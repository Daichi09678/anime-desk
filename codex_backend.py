"""Application state, project-scoped memory, and provider orchestration.

CLI transport and provider-specific protocols live in cli_process.py and
ai_providers.py. This module deliberately has no dependency on Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional
import uuid
import webbrowser

from ai_providers import ProviderState, discover_agy, discover_codex, run_agy, run_codex
from cli_process import ProcessCancelled, resolve_binary
from character_profiles import get_profile


@dataclass
class CodexResult:
    speech: str
    cli_output: str
    saved_memories: List[str]
    emotion: Optional[str] = None
    status: str = "completed"
    technical_output: str = ""
    narration_ja: str = ""


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class CodexBackend:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.config_path = self.base_dir / "config.json"
        self.persona_path = self.base_dir / "persona.txt"
        self._lock = threading.RLock()
        self.config = _read_json(self.config_path, {})
        if not isinstance(self.config, dict):
            self.config = {}
        mem = self.config.get("memory", {})
        self._global_memory_path = self.base_dir / mem.get("file", "memory.json")
        self.ltm_path = self.base_dir / mem.get("ltm_file", "long_term_memory.json")
        self.notes_path = self.base_dir / mem.get("notes_file", "frieren_notes.md")
        # Upgrade the former 10-message default; cap retained history and prompt size.
        self.max_messages = min(100, max(40, int(mem.get("max_messages", 40))))
        codex = self.config.get("codex", {})
        engine = self.config.get("engine", {})
        self.codex_bin = resolve_binary(codex.get("binary", "codex"), "codex")
        self.agy_bin = resolve_binary(engine.get("agy_binary", "agy"), "agy")
        self.model = codex.get("model", "gpt-6-luna")
        self.reasoning_effort = codex.get("reasoning_effort", "low")
        self.timeout_seconds = max(1, int(codex.get("timeout_seconds", 300)))
        self.agy_model = engine.get("agy_model", "gemini-3.8-flash-low")
        self.agy_effort = engine.get("agy_effort", "low")
        self.agy_timeout_seconds = max(1, int(engine.get("agy_timeout_seconds", 300)))
        self.active_engine = "antigravity" if engine.get("active") == "antigravity" else "codex"
        self.providers = {name: ProviderState(name) for name in ("codex", "antigravity")}
        configured_project = self.config.get("project", {}).get("active_dir", "")
        self.project_dir = Path(configured_project).expanduser().resolve() if configured_project else None
        self.project_warning = ""
        if self.project_dir and not self.project_dir.is_dir():
            self.project_warning = f"Folder proyek tidak ditemukan: {self.project_dir}. Pilih ulang folder."
            self.project_dir = None

    @property
    def working_directory(self) -> Path:
        return self.project_dir or Path.home()

    @property
    def character(self):
        return get_profile(self.config.get("ui", {}).get("character", "frieren"))

    def set_character(self, identifier):
        profile = get_profile(identifier)
        if not profile.available(self.base_dir):
            raise ValueError(f"Aset {profile.name} belum tersedia.")
        self.config.setdefault("ui", {})["character"] = profile.id
        self.save_config()

    @property
    def active_model(self) -> str:
        return self.agy_model if self.active_engine == "antigravity" else self.model

    @property
    def project_storage(self) -> Optional[Path]:
        if self.project_dir is None:
            return None
        identity = os.path.normcase(str(self.project_dir.resolve()))
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        return self.base_dir / "data" / "projects" / key

    @property
    def memory_path(self) -> Path:
        storage = self.project_storage
        return storage / "memory.json" if storage else self._global_memory_path

    @property
    def project_ltm_path(self) -> Optional[Path]:
        storage = self.project_storage
        return storage / "facts.json" if storage else None

    def set_project(self, folder: Optional[str]) -> None:
        path = Path(folder).expanduser().resolve() if folder else None
        if path is not None and not path.is_dir():
            raise ValueError("Folder proyek tidak ditemukan.")
        self.project_dir = path
        self.project_warning = ""
        cfg = self.config.setdefault("project", {})
        cfg["active_dir"] = str(path) if path else ""
        if path:
            recent = [str(path)] + [p for p in cfg.get("recent", []) if os.path.normcase(p) != os.path.normcase(str(path))]
            cfg["recent"] = recent[:10]
        self.save_config()

    def save_config(self) -> None:
        with self._lock:
            _write_json(self.config_path, self.config)

    def save_ui_prefs(self, sound_enabled, history_enabled, output_enabled=None,
                      minimized=None, scale=None, opacity=None, bubble_gap=None) -> None:
        ui = self.config.setdefault("ui", {})
        ui.update(sound_enabled=bool(sound_enabled), history_enabled=bool(history_enabled))
        for key, value in (("output_enabled", output_enabled), ("minimized", minimized),
                           ("scale", scale), ("opacity", opacity), ("bubble_gap", bubble_gap)):
            if value is not None:
                ui[key] = value
        self.save_config()

    def set_engine(self, engine_name: str) -> None:
        self.active_engine = "antigravity" if engine_name.lower().startswith("anti") or "agy" in engine_name.lower() else "codex"
        self.config.setdefault("engine", {})["active"] = self.active_engine
        self.save_config()

    def set_model(self, engine: str, model: str) -> None:
        state = self.providers[engine]
        metadata = next((m for m in state.models if m["id"] == model), None)
        if not state.connected or metadata is None:
            raise ValueError("Model belum tersedia. Refresh koneksi/model terlebih dahulu.")
        if engine == "codex":
            self.model = model
            efforts = metadata.get("efforts", [])
            if efforts and self.reasoning_effort not in efforts:
                self.reasoning_effort = metadata.get("default_effort") or efforts[0]
            self.config.setdefault("codex", {}).update(model=model, reasoning_effort=self.reasoning_effort)
        else:
            self.agy_model = model
            self.config.setdefault("engine", {})["agy_model"] = model
        self.set_engine(engine)

    def set_timeout(self, seconds):
        seconds = max(30,min(1800,int(seconds)))
        self.timeout_seconds = self.agy_timeout_seconds = seconds
        self.config.setdefault("codex",{})["timeout_seconds"] = seconds
        self.config.setdefault("engine",{})["agy_timeout_seconds"] = seconds
        self.save_config()

    def discover_providers(self, cancel=None) -> dict[str, ProviderState]:
        states = {}
        # Discovery runs on a UI worker, never from the GUI event loop.
        for name, binary, discover in (("codex", self.codex_bin, discover_codex),
                                       ("antigravity", self.agy_bin, discover_agy)):
            if cancel is not None and cancel.is_set():
                raise ProcessCancelled()
            try:
                states[name] = discover(binary, self.working_directory, cancel)
            except ProcessCancelled:
                raise
            except Exception as exc:
                states[name] = ProviderState(name, message=str(exc)[:800])
        return states

    def check_engine_prerequisites(self) -> tuple[bool, str]:
        binary = self.agy_bin if self.active_engine == "antigravity" else self.codex_bin
        if not (Path(binary).is_file() or shutil.which(binary)):
            return False, f"CLI {self.active_engine} belum ditemukan. Pasang CLI lalu mulai ulang aplikasi."
        state = self.providers[self.active_engine]
        if state.message != "Belum diperiksa" and not state.connected:
            return False, state.message
        return True, state.message if state.connected else "CLI ditemukan; login/koneksi akan diperiksa saat permintaan."

    @property
    def agent_execution_enabled(self):
        return bool(self.config.get("codex", {}).get("agent_execution_enabled", True))

    def set_agent_execution_enabled(self, enabled):
        self.config.setdefault("codex", {})["agent_execution_enabled"] = bool(enabled)
        self.save_config()

    @property
    def gdrive_sync_enabled(self):
        return bool(self.config.get("memory", {}).get("gdrive_sync_enabled", False))

    def set_gdrive_sync_enabled(self, enabled):
        self.config.setdefault("memory", {})["gdrive_sync_enabled"] = bool(enabled)
        self.save_config()
        if enabled:
            self.sync_to_gdrive()

    @property
    def gdrive_account(self):
        return self.config.get("memory", {}).get("gdrive_account", "")

    def get_gdrive_accounts(self):
        return dict(self.config.get("memory", {}).get("gdrive_accounts", {}))

    def set_gdrive_account(self, account):
        self.config.setdefault("memory", {})["gdrive_account"] = account
        self.save_config()
        return self.sync_to_gdrive()

    @property
    def enable_gdrive_plugin(self):
        return bool(self.config.get("codex", {}).get("enable_gdrive_plugin", False))

    def set_enable_gdrive_plugin(self, enabled):
        self.config.setdefault("codex", {})["enable_gdrive_plugin"] = bool(enabled)
        self.save_config()

    def load_persona(self):
        if self.character.id != "frieren":
            return self.character.persona
        if self.persona_path.exists():
            return self.persona_path.read_text(encoding="utf-8").strip()
        return "Kamu adalah Frieren, asisten desktop yang tenang, hangat, dan membantu dalam Bahasa Indonesia."

    def load_memory(self):
        values = _read_json(self.memory_path, [])
        return [m for m in values if isinstance(m, dict)][-self.max_messages:] if isinstance(values, list) else []

    def append_memory(self, role, text, technical_output="", status="completed"):
        with self._lock:
            history = self.load_memory()
            item = {"role": role, "text": text.strip()[:16000], "ts": datetime.now().isoformat(timespec="seconds"), "status": status}
            if role == "assistant":
                item["speaker"] = self.character.name
                item["character"] = self.character.id
            if technical_output:
                item["technical_output"] = technical_output[-24000:]
            history.append(item)
            history = history[-self.max_messages:]
            _write_json(self.memory_path, history)
        return history

    def _finish_user_message(self, status):
        with self._lock:
            history = self.load_memory()
            for item in reversed(history):
                if item.get("role") == "user" and item.get("status") == "pending":
                    item["status"] = status
                    _write_json(self.memory_path, history)
                    break

    def load_ltm(self, scope="global"):
        path = self.project_ltm_path if scope == "project" else self.ltm_path
        values = _read_json(path, []) if path else []
        return [m for m in values if isinstance(m, dict) and isinstance(m.get("fact"), str)] if isinstance(values, list) else []

    def add_ltm(self, fact: str, scope=None):
        scope = scope or ("project" if self.project_dir else "global")
        path = self.project_ltm_path if scope == "project" else self.ltm_path
        if path is None:
            raise ValueError("Pilih folder proyek sebelum menyimpan memori proyek.")
        fact = fact.strip()[:2000]
        if not fact:
            return
        with self._lock:
            facts = self.load_ltm(scope)
            if any(v["fact"].casefold() == fact.casefold() for v in facts):
                return
            facts.append({"fact": fact, "ts": datetime.now().isoformat(timespec="seconds")})
            facts = facts[-100:]
            _write_json(path, facts)
            if scope == "global":
                self._write_markdown_notes(facts)

    def _write_markdown_notes(self, facts):
        text = "# Catatan Frieren — Memori Umum\n\n" + "\n".join(f"- {v.get('fact', '')}" for v in facts)
        self.notes_path.write_text(text + "\n", encoding="utf-8")

    def _sync_pairs(self, target):
        pairs = [(p, target / p.name) for p in (self._global_memory_path, self.ltm_path, self.notes_path)]
        if self.project_storage:
            for path in (self.memory_path, self.project_ltm_path):
                pairs.append((path, target / "projects" / self.project_storage.name / path.name))
        return pairs

    def sync_to_gdrive(self):
        if not self.gdrive_sync_enabled:
            return "Sync Google Drive nonaktif"
        target = self.get_gdrive_accounts().get(self.gdrive_account)
        if not target:
            return "Path Google Drive belum diatur"
        target = Path(target)
        if not target.parent.exists():
            return "Folder Google Drive belum ter-mount"
        try:
            for source, dest in self._sync_pairs(target):
                if source.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
            return "Memori disalin ke folder Google Drive lokal"
        except OSError as exc:
            return f"Gagal sync: {exc}"

    def restore_from_gdrive(self):
        target = self.get_gdrive_accounts().get(self.gdrive_account)
        if not target:
            return "Folder Google Drive belum diatur"
        restored = 0
        for dest, source in self._sync_pairs(Path(target)):
            if source.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                restored += 1
        return f"Memulihkan {restored} file memori"

    def clear_memory(self, include_ltm=False):
        _write_json(self.memory_path, [])
        if include_ltm:
            path = self.project_ltm_path or self.ltm_path
            _write_json(path, [])
            if not self.project_dir:
                self._write_markdown_notes([])
        self.sync_to_gdrive()

    def _try_instant_local_command(self, user_message):
        match = re.match(r"^(?:frieren[, ]+)?(?:tolong\s+)?ingat(?:\s+ya|\s+bahwa|\s+kalau)?[:\s]+(.+)$", user_message.strip(), re.I)
        if match and len(user_message) < 500:
            fact = match.group(1).strip()
            scope = None
            scoped = re.match(r"^(umum|proyek)\s*:\s*(.+)$", fact, re.I | re.S)
            if scoped:
                scope = "global" if scoped.group(1).lower() == "umum" else "project"
                fact = scoped.group(2).strip()
            self.add_ltm(fact, scope)
            reply = "Sudah kucatat. Rinciannya tersedia di output."
            self.append_memory("user", user_message)
            self.append_memory("assistant", reply)
            return CodexResult(reply, f"[Memori tersimpan]\n{fact}", [fact], "senang",
                               technical_output=fact, narration_ja="記録したよ。詳しい内容は出力で確認できるよ。")
        match = re.match(r"^(?:tolong\s+)?(?:buka|bukakan|open)\s+(?:website?\s+)?(https?://\S+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/\S*)?)$", user_message.strip(), re.I)
        if match and self.agent_execution_enabled:
            url = match.group(1)
            if not url.startswith(("https://", "http://")):
                url = "https://" + url
            if not webbrowser.open(url):
                raise RuntimeError("Browser tidak dapat dibuka.")
            reply = f"Sudah kubukakan {url} di browser."
            self.append_memory("user", user_message)
            self.append_memory("assistant", reply)
            return CodexResult(reply, "[Browser dibuka — tanpa panggilan AI]", [], "antusias",
                               narration_ja=f"ブラウザーで {url} を開いたよ。")
        return None

    @staticmethod
    def _is_image_path(path):
        return Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    @staticmethod
    def _relevant_facts(facts, query, limit=12):
        terms = set(re.findall(r"\w{3,}", query.casefold()))
        ranked = sorted(enumerate(facts), key=lambda pair: (
            len(terms.intersection(re.findall(r"\w{3,}", pair[1]["fact"].casefold()))), pair[0]), reverse=True)
        return [item for _, item in ranked[:limit]]

    def build_prompt(self, user_message, attachments=None):
        platform = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
        lines = ["=== PERSONA ===", self.load_persona(), "", f"Sistem operasi: {platform}.",
                 f"Folder kerja aktif: {self.working_directory}",
                 f"Konteks: {'proyek ' + self.project_dir.name if self.project_dir else 'percakapan umum'}.",
                 "Gunakan perintah yang sesuai sistem operasi; jangan menganggap semua sistem memakai perintah macOS open.",
                 "Mode eksekusi: " + ("aktif; lakukan aksi hanya sesuai permintaan pengguna." if self.agent_execution_enabled else "read-only; jangan mengubah file atau membuka aplikasi.")]
        for scope, heading in (("global", "MEMORI UMUM PENGGUNA"), ("project", "MEMORI PROYEK AKTIF")):
            lines += ["", f"=== {heading} ==="]
            lines += ["- " + f["fact"] for f in self._relevant_facts(self.load_ltm(scope), user_message)] or ["(Belum ada)"]
        lines += ["", "=== RIWAYAT KONTEKS ==="]
        # Most recent context wins, including bounded technical details.
        history_lines = []
        remaining = 24000
        for item in reversed(self.load_memory()):
            if item.get("status", "completed") != "completed":
                continue
            text = f"{item.get('role')}: {item.get('text', '')}"
            if item.get("technical_output"):
                text += "\nHasil teknis sebelumnya:\n" + item["technical_output"][-3000:]
            if len(text) > remaining:
                text = text[-remaining:]
            history_lines.append(text)
            remaining -= len(text)
            if remaining <= 0:
                break
        lines += list(reversed(history_lines))
        if attachments:
            lines += ["", "=== LAMPIRAN ==="] + [str(Path(a).resolve()) for a in attachments]
            lines += ["Gambar dikirim sebagai input gambar native. File/folder lain dapat dibaca dari path di atas."]
        lines += ["", "=== PESAN BARU ===", user_message.strip() or "Tolong analisis lampiran ini.", "",
                  "Ucapan utama hangat dan ringkas; berikan detail yang cukup sesuai tugas pengguna.",
                  "Teks jawaban/subtitle wajib bahasa Indonesia. Setelah jawaban dan blok output, tulis "
                  "[VOICE_JA]terjemahan Jepang dari seluruh ucapan utama[/VOICE_JA]. "
                  "Bagian VOICE_JA hanya untuk dubbing suara, bukan subtitle. Gunakan bahasa Jepang alami sesuai persona karakter aktif. "
                  "Makna, angka, hasil, dan kendala harus sama dengan subtitle Indonesia; jangan menambah klaim atau mengganti dengan sapaan. "
                  "Sesuaikan register dan kosakata dengan topik; untuk coding jelaskan hasil, langkah, atau kendala yang benar-benar terjadi. "
                  "Pertahankan kode, path, nama API, dan kutipan yang perlu dalam bahasa aslinya. Jangan sekadar menyapa atau mengulang slogan karakter.",
                  "Letakkan kode/hasil teknis panjang dalam blok ```output ... ```.",
                  "Fakta baru yang relevan dapat ditandai [MEMORY_SAVE: fakta]. Dalam proyek, tag ini menyimpan memori proyek.",
                  "Akhiri dengan [EMOTION: senang|hangat|antusias|penasaran|tenang|ceria|tersentuh|nostalgia|fokus|mengantuk]."]
        return "\n".join(lines)

    def ask(self, user_message, on_status=None, attachments=None, on_text=None, cancel_event=None):
        cancel = cancel_event or threading.Event()
        status = on_status or (lambda text: None)
        emit = on_text or (lambda text: None)
        attachments = [str(Path(a).resolve()) for a in attachments or [] if Path(a).exists()]
        last_emit = 0.0
        latest = ""
        started = time.monotonic()
        logging.info("AI request started: engine=%s model=%s timeout=%s",self.active_engine,self.active_model,
                     self.agy_timeout_seconds if self.active_engine == "antigravity" else self.timeout_seconds)

        def stream(text):
            nonlocal last_emit, latest
            latest = text[:128000]
            if time.monotonic() - last_emit >= 0.08:
                emit(latest)
                last_emit = time.monotonic()

        user_saved = False
        try:
            if cancel.is_set():
                raise ProcessCancelled()
            if not attachments:
                instant = self._try_instant_local_command(user_message)
                if instant is not None:
                    self.sync_to_gdrive()
                    return instant
            ok, reason = self.check_engine_prerequisites()
            if not ok:
                return CodexResult(reason, reason, [], "tenang", "failed")
            if self.project_warning:
                raise RuntimeError(self.project_warning)
            prompt = self.build_prompt(user_message, attachments)
            text = user_message.strip() or "Analisis lampiran"
            if attachments:
                text += "\n[Lampiran: " + ", ".join(Path(a).name for a in attachments) + "]"
            self.append_memory("user", text, status="pending")
            user_saved = True
            status(f"Menghubungkan {self.active_engine} · {self.active_model}…")
            images = [a for a in attachments if self._is_image_path(a)]
            if self.active_engine == "codex":
                reply = run_codex(self.codex_bin, self.model, self.reasoning_effort, prompt, images,
                                  self.working_directory, self.agent_execution_enabled, self.timeout_seconds,
                                  cancel, status, stream, self.enable_gdrive_plugin)
            else:
                reply = run_agy(self.agy_bin, self.agy_model, self.agy_effort, prompt, images,
                                self.working_directory, self.agent_execution_enabled, self.agy_timeout_seconds,
                                cancel, status, stream)
            if cancel.is_set():
                raise ProcessCancelled()
            speech, technical, facts, emotion = self._parse_response(reply.text)
            voice = re.search(r"\[VOICE_JA\](.*?)\[/VOICE_JA\]", reply.text, re.S | re.I)
            narration_ja = voice.group(1).strip() if voice else ""
            if not reply.text.strip():
                raise RuntimeError("Provider tidak mengembalikan teks jawaban.")
            emit(reply.text)
            for fact in facts:
                self.add_ltm(fact)
            self._finish_user_message("completed")
            context = "\n\n".join(part for part in (technical, reply.log) if part)[-24000:]
            self.append_memory("assistant", speech, context)
            self.sync_to_gdrive()
            logging.info("AI request completed in %.1fs",time.monotonic()-started)
            return CodexResult(speech, "\n\n".join(p for p in (reply.log, technical) if p) or speech,
                               facts, emotion, "completed", technical, narration_ja)
        except ProcessCancelled:
            result = CodexResult("Permintaan dibatalkan. Kita bisa lanjut dengan instruksi baru.", "[Dibatalkan]", [], "tenang", "cancelled",
                                 narration_ja="リクエストを中止したよ。新しい指示で続けられるよ。")
        except subprocess.TimeoutExpired as exc:
            seconds = max(1,round(exc.timeout))
            result = CodexResult(f"Batas waktu {seconds} detik tercapai. Perpanjang batas waktu di panel chat atau bagi pekerjaan menjadi lebih kecil.",
                                 f"[Timeout setelah {seconds} detik]", [], "tenang", "timeout",
                                 narration_ja=f"制限時間の{seconds}秒に達したよ。チャット画面で制限時間を延ばすか、作業を分けて試してみて。")
        except Exception as exc:
            result = CodexResult("Ada kendala saat memproses permintaan. Periksa log output untuk rinciannya.", str(exc), [], "tenang", "failed",
                                 narration_ja="処理中に問題が発生したよ。詳しい内容は出力ログを確認してね。")
        if latest.strip():
            partial = self.preview_speech(latest)
            if partial:
                result.speech += "\n\nJawaban sementara (belum selesai):\n" + partial[-6000:]
            result.cli_output += "\n\n[JAWABAN PARSIAL — belum selesai]\n" + latest[-24000:]
            result.technical_output = latest[-24000:]
        logging.info("AI request ended: status=%s elapsed=%.1fs partial_chars=%s",result.status,time.monotonic()-started,len(latest))
        if user_saved:
            self._finish_user_message(result.status)
            self.append_memory("assistant", result.speech, result.technical_output, status=result.status)
        return result

    @staticmethod
    def subtitle_text(text):
        text = re.sub(r"\[VOICE_JA\].*?(?:\[/VOICE_JA\]|$)", "", text, flags=re.S | re.I)
        start = text.rfind("[")
        if start >= 0 and "[VOICE_JA]".startswith(text[start:].upper()):
            text = text[:start]
        return text.strip()

    @staticmethod
    def preview_speech(text):
        text = CodexBackend.subtitle_text(text)
        text = re.sub(r"\[(?:MEMORY_SAVE|EMOTION):[^\]]*(?:\]|$)", "", text, flags=re.I)
        start = text.rfind("[")
        if start >= 0 and any(tag.startswith(text[start:].upper()) for tag in ("[MEMORY_SAVE:", "[EMOTION:")):
            text = text[:start]
        return re.sub(r"```.*?```|```.*$", "", text, flags=re.S).strip()

    @staticmethod
    def _parse_response(raw_text):
        text = CodexBackend.subtitle_text(raw_text)
        text = re.sub(r"^(?:frieren|beatrice|waguri(?: kaoruko)?):\s*", "", text, flags=re.I)
        facts = [m.strip()[:2000] for m in re.findall(r"\[MEMORY_SAVE:\s*(.+?)\]", text, re.I | re.S)]
        match = re.search(r"\[EMOTION:\s*([a-zA-Z_-]+)\s*\]", text, re.I)
        emotion = match.group(1).lower() if match else None
        text = re.sub(r"\[(?:MEMORY_SAVE|EMOTION):[^\]]*\]", "", text, flags=re.I | re.S).strip()
        blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
        speech = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.S).strip()
        return speech or "Hasilnya sudah dirangkum. Lihat panel chat atau output untuk rinciannya.", "\n\n".join(b.strip() for b in blocks), facts, emotion
