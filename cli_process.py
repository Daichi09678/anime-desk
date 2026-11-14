"""Bounded, cancellable subprocess transport shared by both AI providers."""

from __future__ import annotations

import codecs
import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Optional


class ProcessCancelled(Exception):
    pass


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    completed_by_callback: bool = False


class _WindowsJob:
    """Kill owned descendants even if a CLI parent exits before its children."""

    def __init__(self, proc):
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle:
            raise OSError("CreateJobObjectW failed")
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not self.kernel.AssignProcessToJobObject(self.handle, int(proc._handle)):
            self.close()
            raise OSError("Cannot assign CLI to Windows job")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def resolve_binary(configured: str, name: str) -> str:
    """Prefer native executables, including npm's bundled Codex on Windows."""
    path = Path(configured).expanduser()
    if path.is_file():
        return str(path.resolve())
    found = shutil.which(configured) or shutil.which(name)
    if sys.platform == "win32" and name == "codex":
        roots = [Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@openai/codex",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI/Codex/bin"]
        for root in roots:
            if root.is_dir():
                native = next(root.glob("**/codex.exe"), None)
                if native:
                    return str(native)
    return found or configured


class ProcessRunner:
    OUTPUT_LIMIT = 128 * 1024
    LINE_LIMIT = 2 * 1024 * 1024

    def __init__(self, cancel: Optional[threading.Event] = None):
        self.cancel = cancel or threading.Event()
        self.proc: Optional[subprocess.Popen] = None
        self._stop = threading.Event()
        self._outgoing = queue.Queue(maxsize=16)
        self._job = None

    def send(self, message: dict) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("stdin CLI tidak tersedia")
        try:
            self._outgoing.put_nowait((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        except queue.Full:
            raise RuntimeError("Antrean input CLI penuh.")

    def _terminate_tree(self) -> None:
        proc = self.proc
        if proc is None:
            return
        if sys.platform == "win32":
            if self._job is not None:
                self._job.close()
            elif proc.poll() is None:
                try:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    def run(
        self, command: list[str], *, cwd: Path, timeout: float,
        on_stdout: Optional[Callable[[str], bool]] = None,
        on_start: Optional[Callable[["ProcessRunner"], None]] = None,
        input_text: Optional[str] = None, interactive: bool = False,
        on_idle: Optional[Callable[[], bool]] = None,
    ) -> ProcessResult:
        if self.cancel.is_set():
            raise ProcessCancelled()
        deadline = time.monotonic() + timeout
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session": True}
        # npm .cmd shims are a fallback; normal installations resolve to the
        # bundled native executable above. Prompt data always travels via stdin.
        if sys.platform == "win32" and Path(command[0]).suffix.lower() in (".cmd", ".bat"):
            command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", subprocess.list2cmdline(command)]
        self.proc = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={**os.environ, "NO_COLOR": "1"}, **kwargs)
        if sys.platform == "win32":
            try:
                self._job = _WindowsJob(self.proc)
            except OSError:
                self._job = None
        events: queue.Queue = queue.Queue(maxsize=128)

        def put(event):
            while not self._stop.is_set():
                try:
                    events.put(event, timeout=0.05)
                    return
                except queue.Full:
                    pass

        def reader(pipe, channel):
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            pending = ""
            try:
                while not self._stop.is_set():
                    chunk = os.read(pipe.fileno(), 8192)
                    if not chunk:
                        pending += decoder.decode(b"", final=True)
                        break
                    pending += decoder.decode(chunk)
                    while "\n" in pending:
                        line, pending = pending.split("\n", 1)
                        put((channel, line.rstrip("\r")))
                    if len(pending) > self.LINE_LIMIT:
                        put(("reader_error", "Output CLI melebihi batas satu event (2 MB)."))
                        return
                if pending:
                    put((channel, pending))
            except (OSError, ValueError):
                pass
            finally:
                put((channel, None))

        threads = [threading.Thread(target=reader, args=(self.proc.stdout, "stdout"), daemon=True),
                   threading.Thread(target=reader, args=(self.proc.stderr, "stderr"), daemon=True)]
        for thread in threads:
            thread.start()
        output = {"stdout": "", "stderr": ""}
        ended = set()
        completed = False
        writer_error = []

        def writer():
            try:
                if input_text is not None:
                    self.proc.stdin.write(input_text.encode("utf-8"))
                    self.proc.stdin.flush()
                if not interactive:
                    self.proc.stdin.close()
                if on_start:
                    on_start(self)
                while interactive and not self._stop.is_set():
                    try:
                        message = self._outgoing.get(timeout=0.05)
                    except queue.Empty:
                        continue
                    self.proc.stdin.write(message)
                    self.proc.stdin.flush()
            except (OSError, ValueError) as exc:
                writer_error.append(exc)

        writer_thread = threading.Thread(target=writer, daemon=True)
        writer_thread.start()
        try:
            while len(ended) < 2:
                if self.cancel.is_set():
                    raise ProcessCancelled()
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command[:2], timeout)
                if on_idle and on_idle():
                    completed = True
                    break
                if writer_error:
                    raise RuntimeError(f"Tidak dapat mengirim pesan ke CLI: {writer_error[0]}")
                try:
                    channel, line = events.get(timeout=0.05)
                except queue.Empty:
                    continue
                if channel == "reader_error":
                    raise RuntimeError(line)
                if line is None:
                    ended.add(channel)
                    continue
                output[channel] = (output[channel] + line + "\n")[-self.OUTPUT_LIMIT:]
                if channel == "stdout" and on_stdout and on_stdout(line):
                    completed = True
                    break
            if not completed:
                self.proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            return ProcessResult(self.proc.returncode if self.proc.returncode is not None else 0,
                                 output["stdout"], output["stderr"], completed)
        finally:
            self._stop.set()
            self._terminate_tree()
            for thread in threads + [writer_thread]:
                thread.join(timeout=0.5)
            for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
