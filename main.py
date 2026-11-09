"""Entry point for ISP & LAN Diagnostic Center."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.dashboard import DashboardWindow


def main() -> int:
    root = Path(__file__).resolve().parent
    (root / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=root / "logs" / "application.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    app = QApplication([])
    app.setApplicationName("ISP & LAN Diagnostic Center")
    app.setOrganizationName("Local Network Tools")
    window = DashboardWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
