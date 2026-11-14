"""Provider protocols, model discovery, and streamed responses (no Qt dependency)."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
import mimetypes
from pathlib import Path
import time

from cli_process import ProcessRunner


@dataclass
class ProviderState:
    engine: str
    connected: bool = False
    message: str = "Belum diperiksa"
    models: list[dict] = field(default_factory=list)


@dataclass
class ProviderReply:
    text: str
    log: str


INITIALIZE = {"id": 0, "method": "initialize", "params": {
    "clientInfo": {"name": "frieren_desk", "title": "Frieren Desk", "version": "0.2.0"}}}


def _event(line):
    try:
        value = json.loads(line)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _rpc_error(event):
    if event.get("error"):
        error = event["error"]
        raise RuntimeError(error.get("message", str(error)) if isinstance(error, dict) else str(error))


def discover_codex(binary: str, cwd: Path, cancel=None) -> ProviderState:
    runner = ProcessRunner(cancel)
    state = ProviderState("codex")
    account_received = False
    models_received = False
    cursors = set()

    def handle(line):
        nonlocal account_received, models_received
        event = _event(line)
        _rpc_error(event)
        result = event.get("result", {})
        if event.get("id") == 0:
            runner.send({"method": "initialized", "params": {}})
            runner.send({"id": 1, "method": "account/read", "params": {"refreshToken": False}})
            runner.send({"id": 2, "method": "model/list", "params": {"limit": 100, "includeHidden": True}})
        elif event.get("id") == 1:
            account_received = True
            state.connected = result.get("account") is not None or result.get("requiresOpenaiAuth") is False
        elif event.get("id") == 2:
            for model in result.get("data", []):
                identifier = model.get("model") or model.get("id")
                if identifier and not any(m["id"] == identifier for m in state.models):
                    state.models.append({"id": identifier, "name": model.get("displayName") or identifier,
                                         "default": bool(model.get("isDefault")),
                                         "efforts": [v.get("reasoningEffort") for v in model.get("supportedReasoningEfforts", [])],
                                         "default_effort": model.get("defaultReasoningEffort")})
            cursor = result.get("nextCursor")
            if cursor and cursor not in cursors:
                cursors.add(cursor)
                runner.send({"id": 2, "method": "model/list", "params": {"limit": 100, "includeHidden": True, "cursor": cursor}})
            else:
                models_received = True
        return account_received and models_received

    result = runner.run([binary, "app-server"], cwd=cwd, timeout=25, interactive=True,
                        on_start=lambda r: r.send(INITIALIZE), on_stdout=handle)
    if not result.completed_by_callback:
        raise RuntimeError(result.stderr.strip()[-600:] or "Codex menutup koneksi sebelum daftar model diterima.")
    state.message = f"Terhubung · {len(state.models)} model" if state.connected else "Belum login — jalankan codex login"
    return state


def discover_agy(binary: str, cwd: Path, cancel=None) -> ProviderState:
    result = ProcessRunner(cancel).run([binary, "models"], cwd=cwd, timeout=25)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-600:])
    models = []
    for line in result.stdout.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) == 2 and parts[0] and " " not in parts[0]:
            models.append({"id": parts[0], "name": parts[1]})
    if not models:
        raise RuntimeError("AGY tidak mengembalikan daftar model. Periksa login/koneksi dan versi CLI.")
    return ProviderState("antigravity", True, f"Terhubung · {len(models)} model", models)


def run_codex(binary, model, effort, prompt, attachments, cwd, execution, timeout,
              cancel, on_status, on_text, enable_mcp=False):
    """Use the CLI's app-server transport for actual agent-message deltas."""
    runner = ProcessRunner(cancel)
    messages = {}
    logs = []
    finished = False

    def log(text):
        logs.append(str(text)[-4000:])
        if len(logs) > 100:
            del logs[0]

    def handle(line):
        nonlocal finished
        event = _event(line)
        _rpc_error(event)
        result = event.get("result", {})
        params = event.get("params", {})
        method = event.get("method", "")
        if event.get("id") == 0:
            runner.send({"method": "initialized", "params": {}})
            runner.send({"id": 1, "method": "thread/start", "params": {
                "model": model, "cwd": str(cwd), "approvalPolicy": "never",
                "sandbox": "danger-full-access" if execution else "read-only", "ephemeral": True}})
        elif event.get("id") == 1:
            inputs = [{"type": "text", "text": prompt}]
            inputs += [{"type": "localImage", "path": str(Path(a).resolve())} for a in attachments]
            runner.send({"id": 2, "method": "turn/start", "params": {
                "threadId": result["thread"]["id"], "input": inputs, "effort": effort}})
        elif method == "item/agentMessage/delta":
            identifier = params.get("itemId", "reply")
            messages[identifier] = (messages.get(identifier, "") + params.get("delta", ""))[:128000]
            if sum(map(len, messages.values())) > 128000:
                raise RuntimeError("Jawaban melebihi batas 128.000 karakter. Bagi tugas menjadi beberapa permintaan.")
            on_text("\n\n".join(messages.values()))
        elif method in ("item/started", "item/completed"):
            item = params.get("item", {})
            kind = item.get("type")
            if kind == "agentMessage" and method == "item/completed":
                messages[item.get("id", "reply")] = item.get("text", "")[:128000]
                on_text("\n\n".join(messages.values()))
            elif kind == "commandExecution":
                command = item.get("command", "")
                if method == "item/started":
                    log(f"> {command}")
                    on_status(f"Menjalankan perintah: {command[:100]}")
                else:
                    log(item.get("aggregatedOutput", ""))
                    log(f"[exit: {item.get('exitCode')}]")
            elif kind in ("webSearch", "mcpToolCall", "fileChange"):
                on_status({"webSearch": "Menelusuri web…", "fileChange": "Memperbarui file proyek…",
                           "mcpToolCall": "Menggunakan tool…"}[kind])
        elif method == "turn/completed":
            turn = params.get("turn", {})
            if turn.get("status") != "completed":
                error = turn.get("error") or {}
                raise RuntimeError(error.get("message", f"Codex: {turn.get('status', 'gagal')}"))
            finished = True
            return True
        elif "id" in event and method:
            # Do not leave server-initiated requests waiting indefinitely.
            runner.send({"id": event["id"], "error": {"code": -32601, "message": "Interaksi tool ini belum didukung Frieren Desk."}})
        return False

    command = [binary, "app-server"]
    if not enable_mcp:
        command += ["-c", "mcp_servers={}"]
    result = runner.run(command, cwd=cwd, timeout=timeout, interactive=True,
                        on_start=lambda r: r.send(INITIALIZE), on_stdout=handle)
    if not finished:
        raise RuntimeError(result.stderr.strip()[-800:] or "Koneksi Codex berakhir sebelum jawaban selesai.")
    return ProviderReply("\n\n".join(messages.values()).strip(), "\n".join(logs)[-40000:])


def run_agy(binary, model, effort, prompt, images, cwd, execution, timeout,
            cancel, on_status, on_text, keep_alive=None):
    """ACP provides text deltas and explicitly advertises native image support."""
    runner = ProcessRunner(cancel)
    chunks = []
    logs = []
    text_length = 0
    session_id = None
    completed = False
    last_reasoning_status = 0.0
    completed_at = 0.0

    def send_prompt():
        on_status("AGY sedang memproses prompt…")
        if sum(Path(path).stat().st_size for path in images) > 20 * 1024 * 1024:
            raise RuntimeError("Total gambar AGY maksimal 20 MB per pesan agar penggunaan RAM terkendali.")
        content = [{"type": "text", "text": prompt}]
        for image in images:
            path = Path(image)
            if path.stat().st_size > 10 * 1024 * 1024:
                raise RuntimeError("Ukuran gambar AGY maksimal 10 MB per file. Perkecil gambar terlebih dahulu.")
            content.append({"type": "image", "mimeType": mimetypes.guess_type(path.name)[0] or "image/png",
                            "data": base64.b64encode(path.read_bytes()).decode("ascii")})
        runner.send({"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": content}})

    def handle(line):
        nonlocal session_id, completed, text_length, last_reasoning_status, completed_at
        event = _event(line)
        _rpc_error(event)
        result = event.get("result", {})
        if event.get("id") == 0:
            on_status("AGY terhubung · menyiapkan sesi…")
            if images and not result.get("agentCapabilities", {}).get("promptCapabilities", {}).get("image"):
                raise RuntimeError("AGY ini belum mengiklankan dukungan gambar melalui ACP. Gunakan Codex untuk lampiran gambar.")
            runner.send({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(cwd), "mcpServers": []}})
        elif event.get("id") == 1:
            on_status(f"Memilih model AGY · {model}…")
            session_id = result["sessionId"]
            available = result.get("models", {}).get("availableModels", [])
            if not any(m.get("modelId") == model for m in available):
                raise RuntimeError(f"Model AGY {model} tidak tersedia dalam sesi ini. Refresh model.")
            runner.send({"jsonrpc": "2.0", "id": 3, "method": "session/set_model", "params": {"sessionId": session_id, "modelId": model}})
        elif event.get("id") == 3:
            if not execution:
                runner.send({"jsonrpc": "2.0", "id": 4, "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": "plan"}})
            else:
                send_prompt()
        elif event.get("id") == 4:
            send_prompt()
        elif event.get("method") == "session/update":
            update = event.get("params", {}).get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text":
                    delta = content.get("text", "")
                    text_length += len(delta)
                    if text_length > 128000:
                        raise RuntimeError("Jawaban melebihi batas 128.000 karakter. Bagi tugas menjadi beberapa permintaan.")
                    chunks.append(delta)
                    on_text("".join(chunks))
            elif kind in ("tool_call", "tool_call_update"):
                title = update.get("title") or "memeriksa lampiran/tool"
                on_status("AGY · " + title[:120])
                if update.get("title"):
                    logs.append(update["title"][:4000])
                for item in update.get("content", []):
                    content = item.get("content", {})
                    if content.get("type") == "text":
                        logs.append(content.get("text", "")[-4000:])
                logs[:] = logs[-100:]
            elif kind == "agent_thought_chunk" and time.monotonic()-last_reasoning_status >= 2:
                on_status("AGY sedang berpikir…")
                last_reasoning_status = time.monotonic()
        elif event.get("id") == 2:
            if result.get("stopReason") != "end_turn":
                raise RuntimeError(f"AGY menghentikan jawaban: {result.get('stopReason')}")
            completed = True
            completed_at = time.monotonic()
            return keep_alive is None or keep_alive()
        elif event.get("method") == "session/request_permission":
            options = event.get("params", {}).get("options", [])
            choice = next((o for o in options if o.get("kind") == ("allow_once" if execution else "reject_once")), None)
            outcome = {"outcome": "selected", "optionId": choice["optionId"]} if choice else {"outcome": "cancelled"}
            runner.send({"jsonrpc": "2.0", "id": event["id"], "result": {"outcome": outcome}})
        elif "id" in event and event.get("method"):
            runner.send({"jsonrpc": "2.0", "id": event["id"], "error": {"code": -32601, "message": "Client tool belum didukung"}})
        return False

    init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": 1, "clientCapabilities": {},
        "clientInfo": {"name": "frieren-desk", "version": "0.2.0"}}}
    command = [binary, "--model", model, "--effort", effort,
               "--dangerously-skip-permissions" if execution else "--sandbox", "acp"]
    def idle():
        nonlocal completed
        if keep_alive is None or not completed:
            return False
        if keep_alive():
            return True
        if time.monotonic()-completed_at >= 60:
            completed = False
            on_status("Menunggu dan mengumpulkan hasil image-generator…")
            runner.send({"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{
                "sessionId":session_id,"prompt":[{"type":"text","text":"Lanjutkan pekerjaan background yang sudah diluncurkan. Periksa subagent yang sama, ambil hasilnya, salin ke path target yang diminta, dan verifikasi file. Jangan membuat subagent duplikat. Jika masih pending, tunggu/jadwalkan pemeriksaan lagi."}]}})
        return False
    result = runner.run(command, cwd=cwd, timeout=timeout, interactive=True,
                        on_start=lambda r: r.send(init), on_stdout=handle,on_idle=idle)
    if not completed or not chunks:
        raise RuntimeError(result.stderr.strip()[-800:] or "AGY tidak menyelesaikan jawaban.")
    return ProviderReply("".join(chunks), "\n".join(logs)[-40000:])
