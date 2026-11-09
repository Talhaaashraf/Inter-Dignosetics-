import json
from pathlib import Path

from core.report_generator import export_report
from database.database import DiagnosticDatabase


def test_database_saves_and_retrieves_session(tmp_path):
    database = DiagnosticDatabase(tmp_path / "history.sqlite3")
    results = {
        "status": "PASSED",
        "speedtest": {"tests": [{"download_mbps": 7.0, "upload_mbps": 1.2}]},
        "gateway_ping": {"average_ms": 2.0, "packet_loss_percent": 0.0},
        "download_compliance": {"compliance_percent": 100.0},
    }
    session_id = database.save_session(results)
    assert database.get_session(session_id)["results"] == results
    assert database.list_sessions()[0]["download_mbps"] == 7.0


def test_history_retention_only_purges_when_enabled(tmp_path):
    database = DiagnosticDatabase(tmp_path / "history.sqlite3")
    session_id = database.save_session({"status": "PASSED"})
    assert database.purge_older_than(0) == 0
    assert database.get_session(session_id) is not None
    assert database.purge_older_than(1) == 0


def test_report_generates_html_json_csv_and_redacts(tmp_path):
    paths = export_report(
        {"executive_summary": "Local 192.168.1.2", "hostname": "desktop", "findings": []},
        tmp_path, redact=True,
    )
    assert set(paths) == {"json", "html", "csv"}
    for path in paths.values():
        assert Path(path).is_file()
    report = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert report["hostname"] == "[REDACTED]"
    assert "[IP REDACTED]" in report["executive_summary"]
