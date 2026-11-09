import pytest

from core.internet_speed import parse_speedtest_json
from core.package_compliance import bytes_per_second_to_mbps, mbps_to_mbs


def test_mbps_and_mbs_conversion():
    assert mbps_to_mbs(7) == pytest.approx(0.875)
    assert mbps_to_mbs(3.2) == pytest.approx(0.4)


def test_bytes_per_second_conversion():
    assert bytes_per_second_to_mbps(875_000) == pytest.approx(7)


def test_ookla_bandwidth_is_bytes_per_second():
    result = parse_speedtest_json('{"download":{"bandwidth":875000},"upload":{"bandwidth":150000}}')
    assert result["download_mbps"] == pytest.approx(7)
    assert result["upload_mbps"] == pytest.approx(1.2)


def test_speedtest_invalid_json_is_reported():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_speedtest_json("not json")
