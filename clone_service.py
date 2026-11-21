"""Load the local model on demand and release it after a short idle period."""
import atexit
import json
from pathlib import Path
import queue
import threading
import time

from cli_process import ProcessCancelled, ProcessResult, ProcessRunner
from local_voice import runtime


class CloneService:
    def __init__(self, idle_seconds=60):
        self.thread = None
        self.base_dir = None
        self.guard = threading.Lock()
        self.idle_seconds = idle_seconds
        self._idle_timer = None

    def _start_locked(self, base_dir):
        if self.thread and self.thread.is_alive():
            if self.base_dir == Path(base_dir):
                return
            self._stop_locked()
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
        with self.guard:
            self._cancel_idle_timer_locked()
            self._start_locked(base_dir)
            thread, started, runner, events = self.thread, self.started, self.runner, self.events
        deadline = time.monotonic() + 1800
        try:
            while not started.wait(0.05):
                self._check(cancel, deadline)
                if not thread.is_alive():
                    raise RuntimeError(events.get_nowait()[1])
            runner.send(payload)
            while True:
                self._check(cancel, deadline)
                try:
                    kind, value = events.get(timeout=0.05)
                except queue.Empty:
                    continue
                if kind == "error":
                    raise RuntimeError(value)
                try:
                    event = json.loads(value)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("done"):
                    self._schedule_idle_stop(thread)
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
        with self.guard:
            self._stop_locked()

    def _schedule_idle_stop(self, thread):
        with self.guard:
            if self.thread is thread:
                self._idle_timer = threading.Timer(self.idle_seconds, self._stop_if_idle)
                self._idle_timer.daemon = True
                self._idle_timer.start()

    def _stop_if_idle(self):
        with self.guard:
            # A newer request can cancel the timer while this callback waits for the lock.
            if self._idle_timer is threading.current_thread():
                self._stop_locked()

    def _cancel_idle_timer_locked(self):
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _stop_locked(self):
        self._cancel_idle_timer_locked()
        if self.thread:
            self.cancel.set()
            self.thread.join(timeout=7)
            if self.thread.is_alive():
                raise RuntimeError("Mesin cloning belum berhasil dihentikan.")
            self.thread = None


clone_service = CloneService()
atexit.register(clone_service.stop)
