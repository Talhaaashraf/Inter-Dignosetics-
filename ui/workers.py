"""Qt worker for keeping the interface responsive during audits."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Signal

from core.audit import run_complete_audit
from core.network_info import collect_network_info


class NetworkInfoWorker(QThread):
    completed = Signal(dict)

    def run(self):
        try:
            self.completed.emit(collect_network_info())
        except Exception as exc:
            self.completed.emit({"status": "FAILED", "reason": str(exc), "adapters": []})


class AuditWorker(QThread):
    progress = Signal(str, str, str)
    completed = Signal(dict)

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.cancel_event = Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        results = run_complete_audit(
            self.settings, self.cancel_event,
            lambda name, status, message="": self.progress.emit(name, status, message),
        )
        self.completed.emit(results)
