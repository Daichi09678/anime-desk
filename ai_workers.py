"""Qt thread boundaries for chat requests and provider discovery."""

import threading

from PySide6.QtCore import QThread, Signal

from cli_process import ProcessCancelled
from codex_backend import CodexResult


class CodexWorker(QThread):
    finished_result = Signal(object)
    status_update = Signal(str)
    text_update = Signal(str)

    def __init__(self, backend, message, attachments=None, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.message = message
        self.attachments = list(attachments or [])
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            result = self.backend.ask(self.message, on_status=self.status_update.emit,
                                      attachments=self.attachments, on_text=self.text_update.emit,
                                      cancel_event=self.cancel_event)
        except Exception as exc:
            result = CodexResult(f"Permintaan gagal: {exc}", str(exc), [], emotion="tenang", status="failed")
        self.finished_result.emit(result)


class DiscoveryWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            states = self.backend.discover_providers(self.cancel_event)
            if not self.cancel_event.is_set():
                self.ready.emit(states)
        except ProcessCancelled:
            pass
        except Exception as exc:
            self.failed.emit(f"Pemeriksaan model gagal: {exc}")
