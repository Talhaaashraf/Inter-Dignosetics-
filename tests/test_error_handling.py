from threading import Event

import pytest

from core.internet_speed import find_speedtest, run_speedtests
from core.lan_diagnostics import run_iperf_test


def test_missing_speedtest_is_not_available(monkeypatch):
    monkeypatch.setattr("core.internet_speed.find_speedtest", lambda: None)
    result = run_speedtests(1, 0, True, Event())
    assert result["status"] == "NOT AVAILABLE"
    assert "Ookla" in result["reason"]


def test_speedtest_without_consent_is_skipped(monkeypatch):
    monkeypatch.setattr("core.internet_speed.find_speedtest", lambda: "speedtest.exe")
    result = run_speedtests(1, 0, False, Event())
    assert result["status"] == "SKIPPED"


def test_iperf_refuses_public_and_non_ip_hosts():
    assert run_iperf_test("8.8.8.8")["status"] == "SKIPPED"
    assert run_iperf_test("router.local")["status"] == "SKIPPED"


def test_iperf_missing_host_is_not_tested():
    result = run_iperf_test("")
    assert result["status"] == "NOT TESTED"


def test_find_speedtest_returns_optional_path():
    assert find_speedtest() is None or isinstance(find_speedtest(), str)
