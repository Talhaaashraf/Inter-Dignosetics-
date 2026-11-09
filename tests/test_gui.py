import os
import sys

import pytest


def test_gui_initialization_offscreen(monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr("ui.workers.collect_network_info", lambda: {"adapters": []})
    from PySide6.QtWidgets import QApplication

    from ui.dashboard import DashboardWindow

    app = QApplication.instance() or QApplication([])
    window = DashboardWindow()
    assert window.tabs.count() == 4
    assert window.windowTitle() == "ISP & LAN Diagnostic Center"
    window.close()
    if window.network_worker:
        window.network_worker.wait(2000)
    app.processEvents()
