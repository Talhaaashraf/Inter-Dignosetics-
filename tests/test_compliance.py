import pytest

from core.package_compliance import analyze_package, compliance, summarize_speed_tests


THRESHOLDS = {"threshold_good": 90, "threshold_warning": 70, "threshold_poor": 40}


def test_package_compliance_for_reference_speed():
    result = analyze_package(3.2, 7, THRESHOLDS)
    assert result["compliance_percent"] == pytest.approx(45.7142857)
    assert result["difference_mbps"] == pytest.approx(3.8)
    assert result["theoretical_max_mbs"] == pytest.approx(0.875)
    assert result["status"] == "POOR"


def test_upload_package_is_independent_and_optional():
    assert compliance(1.2, None) is None
    assert compliance(1.2, 7) == pytest.approx(17.142857)


def test_speed_test_summary_statistics():
    result = summarize_speed_tests([2, 4, 6], [1, 2, 3])
    assert result["download_average_mbps"] == 4
    assert result["download_median_mbps"] == 4
    assert result["download_variation_mbps"] == 4
    assert result["upload_median_mbps"] == 2
