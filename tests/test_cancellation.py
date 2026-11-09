from threading import Event

from core.audit import run_complete_audit


def test_cancelled_audit_is_marked_cancelled(monkeypatch):
    monkeypatch.setattr("core.audit.collect_network_info", lambda: {
        "adapters": [], "gateway": None, "dns_servers": [],
    })
    monkeypatch.setattr("core.audit.internet_connection", lambda: {"status": "PASSED", "connected": True})
    monkeypatch.setattr("core.audit.run_dns_diagnostics", lambda servers: {"status": "PASSED"})
    monkeypatch.setattr("core.audit.run_traceroute", lambda *args: {"status": "CANCELLED"})
    monkeypatch.setattr("core.audit.run_speedtests", lambda *args: {"status": "CANCELLED", "tests": []})
    monkeypatch.setattr("core.audit.sample_traffic", lambda *args: {"status": "CANCELLED"})
    monkeypatch.setattr("core.audit._wifi_diagnostics", lambda: {"status": "NOT APPLICABLE"})
    monkeypatch.setattr("core.audit.run_iperf_test", lambda *args: {"status": "NOT TESTED"})
    monkeypatch.setattr("core.audit.ping_host", lambda *args: {"status": "CANCELLED"})
    cancel = Event()
    cancel.set()
    result = run_complete_audit(
        {"speed_tests": 1, "ping_count": 1, "traceroute_hops": 1}, cancel
    )
    assert result["status"] == "CANCELLED"
    assert result["check_status"]["audit"] == "CANCELLED"
