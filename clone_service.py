"""Keep the local model warm between utterances; cancellation kills its process tree."""
import atexit
import json
from pathlib import Path
import queue
import threading
import time

from cli_process import ProcessCancelled, ProcessResult, ProcessRunner
from local_voice import runtime


class CloneService:
    def __init__(self):
        self.thread = None
        self.base_dir = None
        self.guard = threading.Lock()

    def start(self, base_dir):
        with self.guard:
            if self.thread and self.thread.is_alive():
                if self.base_dir == Path(base_dir):
                    return
                self.stop()
            self.base_dir = Path(base_dir)
            self.cancel = threading.Event()
            self.started = threading.Event()
            self.events = queue.Queue()
            self.runner = ProcessRunner(self.cancel)
            self.thread = threading.Thread(target=self._serve, daemon=True)
            self.thread.start()

    def _serve(self):
        try:
            result = self.runner.run(
                [str(runtime(self.base_dir)), str(Path(__file__).with_name("local_voice_process.py")), "--serve"],
                cwd=self.base_dir, timeout=86400, interactive=True,
                on_start=lambda runner:self.started.set(),
                on_stdout=lambda line:self.events.put(("line", line)),
            )
            self.events.put(("error", result.stderr[-1200:] or "Mesin cloning berhenti."))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def synthesize(self, base_dir, payload, cancel, on_stdout):
        # The caller serializes requests with CLONE_LOCK.
        if cancel.is_set():
            raise ProcessCancelled()
        self.start(base_dir)
        deadline = time.monotonic() + 1800
        try:
            while not self.started.wait(0.05):
                self._check(cancel, deadline)
                if not self.thread.is_alive():
                    raise RuntimeError(self.events.get_nowait()[1])
            self.runner.send(payload)
            while True:
                self._check(cancel, deadline)
                try:
                    kind, value = self.events.get(timeout=0.05)
                except queue.Empty:
                    continue
                if kind == "error":
                    raise RuntimeError(value)
                try:
                    event = json.loads(value)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("done"):
                    return ProcessResult(1 if event.get("error") else 0, "", event.get("error", ""))
                on_stdout(value)
        except Exception:
            self.stop()
            raise

    @staticmethod
    def _check(cancel, deadline):
        if cancel.is_set():
            raise ProcessCancelled()
        if time.monotonic() >= deadline:
            raise RuntimeError("Cloning melewati batas waktu 1800 detik.")

    def stop(self):
        if self.thread:
            self.cancel.set()
            self.thread.join(timeout=7)
            if self.thread.is_alive():
                raise RuntimeError("Mesin cloning belum berhasil dihentikan.")
            self.thread = None


clone_service = CloneService()
atexit.register(clone_service.stop)
