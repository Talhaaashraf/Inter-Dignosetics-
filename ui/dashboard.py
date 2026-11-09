"""Overview, audit, diagnostic, history, and settings views."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.report_generator import export_report
from database.database import DiagnosticDatabase
from ui.history import HistoryChart
from ui.workers import AuditWorker, NetworkInfoWorker

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "config" / "settings.json"

_STYLE = """
QMainWindow, QWidget { background: #f4f7fb; color: #17243a; font-family: "Segoe UI"; font-size: 10pt; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #e8edf5; padding: 11px 20px; margin: 4px; border-radius: 7px; }
QTabBar::tab:selected { background: #173c70; color: white; }
QLabel#title { font-size: 23pt; font-weight: 700; color: #142b4c; }
QLabel#subtitle { color: #65758b; }
QLabel.metric { background: white; border: 1px solid #e4e9f1; border-radius: 10px; padding: 16px; }
QPushButton { background: #1d5db5; color: white; border: 0; border-radius: 7px; padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: #164a91; }
QPushButton:disabled { background: #a7b3c2; }
QPushButton#cancel { background: #a93737; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox { background: white; border: 1px solid #cbd5e1; border-radius: 5px; padding: 6px; }
QTableWidget { background: white; border: 1px solid #e2e8f0; gridline-color: #edf0f5; }
QHeaderView::section { background: #edf2f8; padding: 7px; border: 0; font-weight: 600; }
QProgressBar { background: white; border: 1px solid #d6deea; border-radius: 5px; height: 18px; text-align: center; }
QProgressBar::chunk { background: #368a68; border-radius: 4px; }
"""


def load_settings() -> dict:
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not load settings; using built-in defaults.")
        return {
            "download_package_mbps": 7.0, "upload_package_mbps": None,
            "speed_tests": 3, "test_interval_seconds": 5, "ping_count": 20,
            "ping_timeout_ms": 1500, "traceroute_hops": 15,
            "threshold_good": 90, "threshold_warning": 70, "threshold_poor": 40,
            "report_directory": "reports", "redact_reports": False,
            "speedtest_consent": False, "history_retention_days": 0,
            "isp_name": "", "reference_download_mbps": 3.2,
            "reference_upload_mbps": 1.2, "lan_iperf_host": "",
        }
    return settings


class DashboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.db = DiagnosticDatabase(ROOT / "data" / "history.sqlite3")
        self.last_results = None
        self.last_report_paths = None
        try:
            recent = self.db.list_sessions(limit=1)
            if recent:
                session = self.db.get_session(recent[0]["id"])
                self.last_results = session.get("results") if session else None
        except Exception:
            logger.exception("Could not load most recent audit")
        self.worker = None
        self.network_worker = None
        self.network_info = {}
        self.setWindowTitle("ISP & LAN Diagnostic Center")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        heading = QVBoxLayout()
        title = QLabel("ISP & LAN Diagnostic Center")
        title.setObjectName("title")
        heading.addWidget(title)
        subtitle = QLabel("Private, read-only Windows network diagnostics")
        subtitle.setObjectName("subtitle")
        heading.addWidget(subtitle)
        layout.addLayout(heading)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.dashboard_page = QWidget()
        self.audit_page = QWidget()
        self.history_page = QWidget()
        self.settings_page = QWidget()
        self.tabs.addTab(self.dashboard_page, "Overview")
        self.tabs.addTab(self.audit_page, "Complete Audit")
        self.tabs.addTab(self.history_page, "History & Reports")
        self.tabs.addTab(self.settings_page, "Settings")
        self._build_dashboard()
        self._build_audit()
        self._build_history()
        self._build_settings()
        self.refresh_dashboard()
        self.refresh_history()

    def _build_dashboard(self):
        layout = QVBoxLayout(self.dashboard_page)
        self.status_label = QLabel("Ready — no diagnostic has been run yet.")
        self.status_label.setStyleSheet("font-size:14pt;font-weight:600;padding:10px")
        layout.addWidget(self.status_label)
        self.cards = {}
        names = [
            ("Package", "package"), ("Download", "download"), ("Upload", "upload"),
            ("Ethernet link", "link"), ("Active adapter", "adapter"),
            ("Local IPv4", "ip"), ("Default gateway", "gateway"),
            ("DNS servers", "dns"), ("Internet", "internet"),
            ("Average latency", "latency"), ("Packet loss", "loss"),
            ("VPN / proxy", "proxy"),
        ]
        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (caption, key) in enumerate(names):
            card = QLabel(f"{caption}\nNot measured")
            card.setObjectName("metric")
            card.setProperty("class", "metric")
            card.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            card.setMinimumHeight(78)
            self.cards[key] = (caption, card)
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        self.dashboard_note = QLabel("User-provided reference speeds (3.2 Mbps down / 1.2 Mbps up) are not verified measurements.")
        self.dashboard_note.setWordWrap(True)
        self.dashboard_note.setObjectName("subtitle")
        layout.addWidget(self.dashboard_note)
        layout.addStretch()
        button = QPushButton("RUN COMPLETE NETWORK AUDIT")
        button.clicked.connect(lambda: (self.tabs.setCurrentWidget(self.audit_page), self.start_audit()))
        layout.addWidget(button)

    def _build_audit(self):
        layout = QVBoxLayout(self.audit_page)
        intro = QLabel("Read-only checks run in background workers. Ookla testing requires explicit consent in Settings.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        controls = QHBoxLayout()
        self.run_button = QPushButton("RUN COMPLETE NETWORK AUDIT")
        self.run_button.clicked.connect(self.start_audit)
        self.cancel_button = QPushButton("Cancel audit")
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_audit)
        self.export_button = QPushButton("Export latest report")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_latest)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.export_button)
        controls.addStretch()
        layout.addLayout(controls)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.audit_table = QTableWidget(0, 3)
        self.audit_table.setHorizontalHeaderLabels(["Diagnostic", "Status", "Details"])
        self.audit_table.horizontalHeader().setStretchLastSection(True)
        self.audit_table.horizontalHeader().setDefaultSectionSize(210)
        self.audit_table.setAlternatingRowColors(True)
        layout.addWidget(self.audit_table)

    def _build_history(self):
        layout = QVBoxLayout(self.history_page)
        controls = QHBoxLayout()
        self.history_range = QComboBox()
        self.history_range.addItem("Daily", 1)
        self.history_range.addItem("Weekly", 7)
        self.history_range.addItem("Monthly", 30)
        self.history_range.currentIndexChanged.connect(self.refresh_history)
        refresh = QPushButton("Refresh history")
        refresh.clicked.connect(self.refresh_history)
        compare = QPushButton("Compare selected sessions")
        compare.clicked.connect(self.compare_sessions)
        export_csv = QPushButton("Export history CSV")
        export_csv.clicked.connect(self.export_history)
        controls.addWidget(self.history_range)
        controls.addWidget(refresh)
        controls.addWidget(compare)
        controls.addWidget(export_csv)
        controls.addStretch()
        layout.addLayout(controls)
        self.history_table = QTableWidget(0, 8)
        self.history_table.setHorizontalHeaderLabels([
            "Session", "Date (UTC)", "Status", "Download Mbps", "Upload Mbps",
            "Latency ms", "Loss %", "Package compliance %",
        ])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.history_table)
        self.history_chart = HistoryChart()
        layout.addWidget(self.history_chart)
        self.history_note = QLabel("Sessions and reports are stored locally; records are preserved until you remove the database.")
        self.history_note.setObjectName("subtitle")
        layout.addWidget(self.history_note)

    def _build_settings(self):
        outer = QVBoxLayout(self.settings_page)
        form = QFormLayout()
        self.setting_widgets = {}

        def line(key, label, default=""):
            field = QLineEdit(str(self.settings.get(key, default) or ""))
            self.setting_widgets[key] = field
            form.addRow(label, field)

        def number(key, label, value, low, high, decimals=0):
            widget = QDoubleSpinBox() if decimals else QSpinBox()
            widget.setRange(low, high)
            if decimals:
                widget.setDecimals(decimals)
                widget.setSingleStep(0.1)
            widget.setValue(float(self.settings.get(key, value) or value))
            self.setting_widgets[key] = widget
            form.addRow(label, widget)

        line("isp_name", "ISP name")
        self.speed_units = QComboBox()
        self.speed_units.addItems(["Mbps", "MB/s"])
        self.speed_units.setCurrentText(self.settings.get("speed_units", "Mbps"))
        form.addRow("Dashboard speed unit", self.speed_units)
        number("download_package_mbps", "Download package (Mbps)", 7, 0.1, 100000, 1)
        self.upload_known = QCheckBox("Configure upload package speed")
        self.upload_known.setChecked(self.settings.get("upload_package_mbps") is not None)
        self.upload_value = QDoubleSpinBox()
        self.upload_value.setRange(0.1, 100000)
        self.upload_value.setDecimals(1)
        self.upload_value.setValue(float(self.settings.get("upload_package_mbps") or 1))
        form.addRow(self.upload_known, self.upload_value)
        number("reference_download_mbps", "Reference download (Mbps; unverified)", 3.2, 0, 100000, 1)
        number("reference_upload_mbps", "Reference upload (Mbps; unverified)", 1.2, 0, 100000, 1)
        number("speed_tests", "Ookla test count (1–3)", 3, 1, 3)
        number("test_interval_seconds", "Interval between tests (seconds)", 5, 0, 300)
        number("ping_count", "Ping requests", 20, 1, 100)
        number("ping_timeout_ms", "Ping timeout (ms)", 1500, 100, 10000)
        number("traceroute_hops", "Traceroute hop limit", 15, 1, 30)
        number("threshold_good", "GOOD threshold (%)", 90, 1, 100, 1)
        number("threshold_warning", "WARNING threshold (%)", 70, 1, 100, 1)
        number("threshold_poor", "POOR threshold (%)", 40, 1, 100, 1)
        line("report_directory", "Report folder (relative to project or absolute)", "reports")
        number("history_retention_days", "History retention in days (0 = preserve all)", 0, 0, 36500)
        line("lan_iperf_host", "Optional authorized iperf3 server address")
        self.consent = QCheckBox("I accept the Ookla CLI license and its test/data terms; tests contact Ookla and a selected test server.")
        self.consent.setChecked(bool(self.settings.get("speedtest_consent")))
        form.addRow("External speed test consent", self.consent)
        self.redact = QCheckBox("Redact identifying data from exported reports")
        self.redact.setChecked(bool(self.settings.get("redact_reports")))
        form.addRow("Report privacy", self.redact)
        outer.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton("Save settings")
        save.clicked.connect(self.save_settings)
        buttons.addWidget(save)
        buttons.addStretch()
        outer.addLayout(buttons)
        outer.addStretch()

    def save_settings(self):
        if not self.save_settings_silently():
            return
        try:
            self._persist_settings()
        except OSError as exc:
            logger.exception("Failed to save settings")
            QMessageBox.critical(self, "Settings error", f"Could not save settings: {exc}")

    def refresh_dashboard(self):
        if self.network_worker and self.network_worker.isRunning():
            return
        self.network_worker = NetworkInfoWorker()
        self.network_worker.completed.connect(self.display_network_info)
        self.network_worker.start()

    def display_network_info(self, info):
        try:
            self.network_info = info
            adapters = info.get("adapters", [])
            active = next((adapter for adapter in adapters if adapter.get("is_up")), None)
            ipv4 = None
            if active:
                ipv4 = next((item["address"] for item in active["addresses"] if item["family"].endswith("AF_INET")), None)

            unit = self.settings.get("speed_units", "Mbps")

            def format_speed(value):
                if value is None:
                    return "Unavailable"
                adjusted = value / 8 if unit == "MB/s" else value
                return f"{adjusted:.2f} {unit}"

            values = {
                "package": f"{format_speed(self.settings.get('download_package_mbps', 7))} down",
                "download": "Not measured", "upload": "Not measured",
                "link": f"{active['speed_mbps']} Mbps" if active and active.get("speed_mbps") else "Not available",
                "adapter": active["name"] if active else "Not detected",
                "ip": ipv4 or "Not available",
                "gateway": info.get("gateway") or "Not detected",
                "dns": ", ".join(info.get("dns_servers", [])) or "Not detected",
                "internet": "Run audit to test", "latency": "Not measured", "loss": "Not measured",
                "proxy": "Detected" if info.get("proxy_detected") else "Not detected",
            }
            if self.last_results:
                speed = self.last_results.get("speed_summary", {})
                values["download"] = format_speed(speed.get("download_average_mbps"))
                values["upload"] = format_speed(speed.get("upload_average_mbps"))
                ping = self.last_results.get("gateway_ping", {})
                values["latency"] = f"{ping['average_ms']:.1f} ms" if isinstance(ping.get("average_ms"), (int, float)) else "Unavailable"
                values["loss"] = f"{ping['packet_loss_percent']:.1f}%" if isinstance(ping.get("packet_loss_percent"), (int, float)) else "Unavailable"
                internet = self.last_results.get("internet_connection", {})
                values["internet"] = "Connected" if internet.get("connected") else "Unconfirmed"
                self.status_label.setText(f"Last audit: {self.last_results.get('status', 'UNKNOWN')} — {self.last_results.get('finished_at', '')}")
            else:
                self.status_label.setText("Ready — run a complete audit to measure your connection.")
            for key, (caption, label) in self.cards.items():
                label.setText(f"{caption}\n{values[key]}")
        except Exception as exc:
            logger.exception("Dashboard network refresh failed")
            self.status_label.setText(f"Network information unavailable: {exc}")

    def start_audit(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.save_settings_silently():
            return
        try:
            self._persist_settings()
        except OSError as exc:
            logger.exception("Failed to save settings before audit")
            QMessageBox.critical(self, "Settings error", f"Could not save settings: {exc}")
            return
        self.audit_table.setRowCount(0)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.show()
        self.worker = AuditWorker(dict(self.settings))
        self.worker.progress.connect(self.on_progress)
        self.worker.completed.connect(self.on_audit_complete)
        self.worker.start()

    def save_settings_silently(self):
        for key, widget in self.setting_widgets.items():
            if isinstance(widget, QLineEdit):
                self.settings[key] = widget.text().strip()
            else:
                value = widget.value()
                self.settings[key] = int(value) if isinstance(widget, QSpinBox) else float(value)
        self.settings["upload_package_mbps"] = self.upload_value.value() if self.upload_known.isChecked() else None
        self.settings["speed_units"] = self.speed_units.currentText()
        self.settings["speedtest_consent"] = self.consent.isChecked()
        self.settings["redact_reports"] = self.redact.isChecked()
        if not (self.settings["threshold_good"] > self.settings["threshold_warning"] > self.settings["threshold_poor"] > 0):
            QMessageBox.warning(self, "Invalid thresholds", "Thresholds must descend: GOOD > WARNING > POOR > 0.")
            return False
        return True

    def _persist_settings(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        self.refresh_dashboard()

    def on_progress(self, name, status, message):
        row = next((index for index in range(self.audit_table.rowCount())
                    if self.audit_table.item(index, 0).text() == name), None)
        if row is None:
            row = self.audit_table.rowCount()
            self.audit_table.insertRow(row)
            self.audit_table.setItem(row, 0, QTableWidgetItem(name.replace("_", " ").title()))
        self.audit_table.setItem(row, 1, QTableWidgetItem(status))
        self.audit_table.setItem(row, 2, QTableWidgetItem(message))

    def cancel_audit(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancellation requested; active checks are stopping.")

    def on_audit_complete(self, results):
        self.last_results = results
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.hide()
        self.export_button.setEnabled(True)
        try:
            session_id = self.db.save_session(results)
            retention_days = int(self.settings.get("history_retention_days", 0))
            if retention_days > 0:
                self.db.purge_older_than(retention_days)
            self.status_label.setText(f"Audit {session_id} complete: {results['status']}")
        except Exception as exc:
            logger.exception("Could not store audit session")
            QMessageBox.critical(self, "History error", f"Audit completed, but history could not be saved: {exc}")
        self.refresh_dashboard()
        self.refresh_history()
        self.export_latest(show_dialog=False)

    def export_latest(self, show_dialog=True):
        if not self.last_results:
            return
        directory = Path(self.settings.get("report_directory") or "reports")
        if not directory.is_absolute():
            directory = ROOT / directory
        try:
            paths = export_report(self.last_results, directory, self.settings.get("redact_reports", False))
            self.last_report_paths = paths
            if show_dialog:
                QMessageBox.information(self, "Report exported", "\n".join(paths.values()))
        except (OSError, ValueError, TypeError) as exc:
            logger.exception("Report export failed")
            if show_dialog:
                QMessageBox.critical(self, "Report error", f"Could not export report: {exc}")
            else:
                self.status_label.setText(f"Audit complete; report export failed: {exc}")

    def refresh_history(self):
        try:
            records = self.db.list_sessions()
            days = int(self.history_range.currentData()) if hasattr(self, "history_range") else 30
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            filtered = []
            for record in records:
                try:
                    created = datetime.fromisoformat(record["created_at"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if created >= cutoff:
                        filtered.append(record)
                except (TypeError, ValueError):
                    logger.warning("Skipping malformed session timestamp %r", record.get("created_at"))
            records = filtered
            self.history_table.setRowCount(len(records))
            for row, record in enumerate(records):
                values = [
                    record["id"], record["created_at"], record["status"],
                    record["download_mbps"], record["upload_mbps"], record["latency_ms"],
                    record["packet_loss_percent"], record["compliance_percent"],
                ]
                for column, value in enumerate(values):
                    shown = f"{value:.2f}" if isinstance(value, float) else str(value if value is not None else "—")
                    self.history_table.setItem(row, column, QTableWidgetItem(shown))
            self.history_chart.set_records(records)
        except Exception as exc:
            logger.exception("History refresh failed")
            self.history_note.setText(f"History could not be loaded: {exc}")

    def compare_sessions(self):
        selected = sorted({index.row() for index in self.history_table.selectionModel().selectedRows()})
        if len(selected) != 2:
            QMessageBox.information(self, "Compare sessions", "Select exactly two history rows.")
            return
        ids = [int(self.history_table.item(row, 0).text()) for row in selected]
        first, second = (self.db.get_session(session_id) for session_id in ids)
        if not first or not second:
            QMessageBox.warning(self, "Compare sessions", "One of the selected sessions is no longer available.")
            return
        metrics = ("download_mbps", "upload_mbps", "latency_ms", "packet_loss_percent", "compliance_percent")
        lines = [f"Session {first['id']} vs session {second['id']}"]
        for key in metrics:
            left, right = first.get(key), second.get(key)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                lines.append(f"{key.replace('_', ' ').title()}: {left:.2f} vs {right:.2f} (change {right-left:+.2f})")
            else:
                lines.append(
                    f"{key.replace('_', ' ').title()}: "
                    f"{left if left is not None else '—'} vs {right if right is not None else '—'}"
                )
        QMessageBox.information(self, "Session comparison", "\n".join(lines))

    def export_history(self):
        target, _ = QFileDialog.getSaveFileName(self, "Export history", str(ROOT / "reports" / "history.csv"), "CSV files (*.csv)")
        if not target:
            return
        try:
            records = self.db.list_sessions(limit=100000)
            if not records:
                QMessageBox.information(self, "History", "There are no stored sessions.")
                return
            import csv
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(records)
            QMessageBox.information(self, "History exported", target)
        except OSError as exc:
            logger.exception("History export failed")
            QMessageBox.critical(self, "Export error", str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.finished.connect(self.close)
            event.ignore()
            return
        if self.network_worker and self.network_worker.isRunning():
            self.network_worker.finished.connect(self.close)
            event.ignore()
            return
        event.accept()
