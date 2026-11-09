import pytest

from core.router_diagnostics import parse_ping_output
from core.traceroute_diagnostics import parse_traceroute


def test_windows_ping_statistics_and_jitter():
    output = """Reply from 192.168.1.1: bytes=32 time=1ms TTL=64
Reply from 192.168.1.1: bytes=32 time=3ms TTL=64
Packets: Sent = 3, Received = 2, Lost = 1 (33% loss),
Minimum = 1ms, Maximum = 3ms, Average = 2ms"""
    result = parse_ping_output(output)
    assert result["sent"] == 3
    assert result["received"] == 2
    assert result["packet_loss_percent"] == pytest.approx(100 / 3)
    assert result["jitter_estimate_ms"] == 2


def test_ping_no_responses_is_not_internet_failure():
    result = parse_ping_output("Request timed out.")
    assert result["status"] == "WARNING"
    assert result["packet_loss_percent"] is None


def test_windows_traceroute_parsing_keeps_timeouts():
    hops = parse_traceroute(
        "Tracing route to 1.1.1.1 over a maximum of 3 hops\n"
        "  1    <1 ms     2 ms     1 ms  192.168.1.1\n"
        "  2     *        *        *     Request timed out.\n"
        "  3    15 ms    14 ms    16 ms  1.1.1.1\n"
    )
    assert len(hops) == 3
    assert hops[0]["ip"] == "192.168.1.1"
    assert hops[1]["timed_out"] is True
    assert hops[2]["average_ms"] == 15
