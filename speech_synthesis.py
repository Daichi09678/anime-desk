"""Cancellable Japanese narration using local cloning or explicit synthetic engines."""

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import threading
import uuid

from PySide6.QtCore import QThread, Signal
from mutagen import File, MutagenError

from character_profiles import PROFILES
from cli_process import ProcessCancelled, ProcessRunner
from local_voice import reference_for, cpu_settings
from clone_service import clone_service

CLONE_LOCK = threading.Lock()


STYLES = {
    "frieren": {"voice":"ja-JP-NanamiNeural","rate":-12,"pitch":-4,"system_rate":-2},
    "beatrice": {"voice":"ja-JP-NanamiNeural","rate":-3,"pitch":-9,"system_rate":-1},
    "waguri_kaoruko": {"voice":"ja-JP-NanamiNeural","rate":0,"pitch":8,"system_rate":0},
}


def narration_text(text):
    text = re.sub(r"```.*?```", "",text,flags=re.S)
    text = re.sub(r"\[(?:MEMORY_SAVE|EMOTION):[^\]]*\]", "",text,flags=re.I)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)",r"\1",text)
    text = re.sub(r"https?://\S+","リンク先",text)
    text = re.sub(r"[*_#`~]","",html.unescape(text))
    text = re.sub(r"[\U00010000-\U0010ffff]","",text)
    return re.sub(r"\s+"," ",text).strip()[:4000]


def speech_style(character, emotion):
    style = dict(STYLES.get(character,STYLES["frieren"]))
    if emotion in ("senang","ceria","antusias"):
        style["rate"] += 3
        style["pitch"] += 2
    elif emotion in ("mengantuk","nostalgia","tenang"):
        style["rate"] -= 3
    return style


def narration_chunks(text):
    """Keep the first audio short without dropping any part of the answer."""
    return [sentence[i:i+160] for sentence in
            re.findall(r"[^。！？!?]+[。！？!?]?", text)
            for i in range(0, len(sentence), 160) if sentence[i:i+160].strip()]


@dataclass
class NarrationAudio:
    file: Path
    duration_ms: int
    engine: str


def _cached_audio(path, engine):
    if not path.is_file() or path.stat().st_size < 100:
        return None
    info = File(str(path))
    duration = round(info.info.length * 1000) if info is not None else 0
    return NarrationAudio(path, duration, engine) if duration > 0 else None


class NarrationWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, base_dir, character, text, emotion=None, engine="auto", parent=None):
        super().__init__(parent)
        self.base_dir = Path(base_dir)
        self.character = character
        self.text = narration_text(text)
        self.style = speech_style(character,emotion)
        self.engine = engine
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        if self.engine == "fast":
            if self.cancel_event.is_set():
                return
            audio = self._ready_greeting()
            if audio:
                if not self.cancel_event.is_set():
                    self.ready.emit(audio)
            else:
                self.engine = "edge"
                self._synthesize()
            return
        if self.engine == "qwen-local":
            self._synthesize()
            return
        for chunk in narration_chunks(self.text) or [""]:
            if self.cancel_event.is_set():
                break
            self.text = chunk
            if not self._synthesize():
                break

    def _greeting_folder(self):
        profile = PROFILES.get(self.character)
        if profile and self.text in map(narration_text, profile.voice_taps):
            return self.base_dir / "data/tts/presets" / self.character
        return None

    def _cache_key(self, engine, reference, tuning):
        # Qwen uses the character reference, not Edge's emotion/rate/pitch.
        cache_style = None if engine == "qwen-local" else self.style
        identity = [self.text, cache_style, engine, reference, tuning, "ja-clone-v3"]
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]

    def _ready_greeting(self):
        folder = self._greeting_folder()
        if folder is None:
            return None
        try:
            key = self._cache_key("qwen-local", reference_for(self.base_dir, self.character),
                                  cpu_settings(self.base_dir))
            return _cached_audio(folder / f"{key}_qwen-local.wav", "qwen-local")
        except (OSError, ValueError, TypeError, KeyError, MutagenError):
            return None

    def _synthesize(self):
        try:
            if not self.text:
                if not self.cancel_event.is_set():
                    self.failed.emit("Tidak ada teks yang dapat dinarasikan.")
                return
            preset_folder = self._greeting_folder() if self.engine == "qwen-local" else None
            folder = preset_folder or self.base_dir / "data/tts" / self.character
            folder.mkdir(parents=True,exist_ok=True)
            reference = reference_for(self.base_dir, self.character) if self.engine == "qwen-local" else None
            tuning = cpu_settings(self.base_dir) if self.engine == "qwen-local" else None
            key = self._cache_key(self.engine, reference, tuning)
            python = Path(sys.executable)
            console = python.with_name("python.exe") if sys.platform == "win32" else python
            if not console.is_file():
                console = python
            engines = ["edge","windows"] if self.engine == "auto" and sys.platform == "win32" else ["edge" if self.engine == "auto" else self.engine]
            errors = []
            for engine in engines:
                if self.cancel_event.is_set():
                    raise ProcessCancelled()
                output = folder / f"{key}_{engine}{'.wav' if engine in ('windows','qwen-local') else '.mp3'}"
                temporary = output.with_name(output.stem+"."+uuid.uuid4().hex+".part"+output.suffix)
                try:
                    if not output.is_file() or output.stat().st_size < 100:
                        payload = {"text":self.text,"style":self.style,"output":str(temporary),"engine":engine}
                        if engine == "qwen-local":
                            payload["reference"] = reference
                            # CPU synthesis is slower than playback. Publish the
                            # complete WAV, otherwise every sentence underruns.
                            payload["stream_chunks"] = False
                            while not CLONE_LOCK.acquire(timeout=0.1):
                                if self.cancel_event.is_set():
                                    raise ProcessCancelled()
                            try:
                                if self.cancel_event.is_set():
                                    raise ProcessCancelled()
                                result = clone_service.synthesize(self.base_dir, payload, self.cancel_event, lambda line:None)
                            finally:
                                CLONE_LOCK.release()
                        else:
                            result = ProcessRunner(self.cancel_event).run(
                                [str(console),str(Path(__file__).with_name("tts_process.py"))],
                                cwd=self.base_dir,timeout=50,input_text=json.dumps(payload,ensure_ascii=False))
                        if result.returncode or not temporary.is_file() or temporary.stat().st_size < 100:
                            raise RuntimeError(result.stderr[-600:] or "TTS tidak menghasilkan audio.")
                        temporary.replace(output)
                    audio = _cached_audio(output, engine)
                    if audio is None:
                        raise RuntimeError("Durasi narasi tidak valid.")
                    if preset_folder is None:
                        # Never delete preset greetings or chunks still queued for playback.
                        import time
                        for old in folder.glob("*"):
                            try:
                                if old == output or time.time() - old.stat().st_mtime < 86400 or not old.is_file():
                                    continue
                                old.unlink()
                            except OSError:
                                pass
                    if not self.cancel_event.is_set():
                        self.ready.emit(audio)
                    return True
                except ProcessCancelled:
                    raise
                except Exception as exc:
                    errors.append(f"{engine}: {exc}")
                finally:
                    temporary.unlink(missing_ok=True)
            self.failed.emit("; ".join(errors)[-800:])
        except ProcessCancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))
