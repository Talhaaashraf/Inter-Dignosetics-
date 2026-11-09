"""Bandwidth unit conversion and ISP package comparisons."""

from __future__ import annotations

from statistics import median
from typing import Iterable


def bytes_per_second_to_mbps(value: float) -> float:
    """Convert decimal bytes/second into megabits/second."""
    return value * 8 / 1_000_000


def mbps_to_mbs(value: float) -> float:
    """Convert megabits/second into megabytes/second."""
    return value / 8


def compliance(actual_mbps: float | None, package_mbps: float | None) -> float | None:
    if actual_mbps is None or package_mbps is None or package_mbps <= 0:
        return None
    return actual_mbps / package_mbps * 100


def summarize_speed_tests(downloads: Iterable[float], uploads: Iterable[float]) -> dict:
    down = list(downloads)
    up = list(uploads)
    return {
        "download_average_mbps": sum(down) / len(down) if down else None,
        "download_median_mbps": median(down) if down else None,
        "download_min_mbps": min(down) if down else None,
        "download_max_mbps": max(down) if down else None,
        "download_variation_mbps": max(down) - min(down) if down else None,
        "upload_average_mbps": sum(up) / len(up) if up else None,
        "upload_median_mbps": median(up) if up else None,
    }


def analyze_package(actual_mbps: float | None, package_mbps: float | None,
                    thresholds: dict) -> dict:
    achieved = compliance(actual_mbps, package_mbps)
    if achieved is None:
        status = "INSUFFICIENT DATA"
    elif achieved >= thresholds["threshold_good"]:
        status = "GOOD"
    elif achieved >= thresholds["threshold_warning"]:
        status = "WARNING"
    elif achieved >= thresholds["threshold_poor"]:
        status = "POOR"
    else:
        status = "CRITICAL"
    return {
        "package_mbps": package_mbps,
        "actual_mbps": actual_mbps,
        "compliance_percent": achieved,
        "difference_mbps": package_mbps - actual_mbps if package_mbps is not None and actual_mbps is not None else None,
        "remaining_mbps": max(0, package_mbps - actual_mbps) if package_mbps is not None and actual_mbps is not None else None,
        "theoretical_max_mbs": mbps_to_mbs(package_mbps) if package_mbps is not None else None,
        "actual_mbs": mbps_to_mbs(actual_mbps) if actual_mbps is not None else None,
        "status": status,
        "threshold_note": "Troubleshooting indicators only; not an ISP service-level guarantee.",
    }
