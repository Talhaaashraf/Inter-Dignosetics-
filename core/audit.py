"""Background-capable orchestration for the complete read-only audit."""

from __future__ import annotations

import concurrent.futures
import logging
import socket
from datetime import datetime, timezone
from threading import Event

from core.dns_diagnostics import run_dns_diagnostics
from core.internet_speed import run_speedtests
from core.lan_diagnostics import run_iperf_test
from core.network_info import collect_network_info, internet_connection
from core.package_compliance import analyze_package, summarize_speed_tests
from core.root_cause_analysis import analyze_findings
from core.router_diagnostics import ping_host
from core.traceroute_diagnostics import run_traceroute
from core.traffic_monitor import sample_traffic

logger = logging.getLogger(__name__)


def _wifi_diagnostics() -> dict:
    import platform
    import shutil
    import subprocess

    if platform.system() != "Windows":
        return {"status": "NOT APPLICABLE", "reason": "Windows Wi-Fi diagnostics are unavailable on this operating system."}
    executable = shutil.which("netsh.exe") or shutil.which("netsh")
    if not executable:
        return {"status": "NOT AVAILABLE", "reason": "Windows netsh executable not found."}
    try:
        completed = subprocess.run(
            [executable, "wlan", "show", "interfaces"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "FAILED", "reason": str(exc)}
    if completed.returncode or "There is no wireless interface" in completed.stdout:
        return {"status": "NOT APPLICABLE", "reason": "No connected or available Wi-Fi interface was reported."}
    parsed = {}
    labels = {
        "Name": "adapter", "Description": "description", "State": "state",
        "SSID": "ssid", "Signal": "signal_percent", "Radio type": "radio_type",
        "Channel": "channel", "Receive rate (Mbps)": "receive_mbps",
        "Transmit rate (Mbps)": "transmit_mbps", "BSSID": "bssid",
    }
    for line in completed.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in labels:
            parsed[labels[key]] = value
    if not parsed:
        return {"status": "NOT AVAILABLE", "reason": "Wi-Fi output format was not recognized."}
    parsed["status"] = "PASSED"
    parsed["note"] = "Output field names can be localized by Windows; unavailable fields are omitted."
    return parsed


def run_complete_audit(settings: dict, cancel_event: Event, progress=None) -> dict:
    def report(name: str, status: str, message: str = ""):
        if progress:
            progress(name, status, message)

    started = datetime.now(timezone.utc)
    results = {
        "started_at": started.isoformat(),
        "settings_snapshot": {
            key: value for key, value in settings.items()
            if key not in {"speedtest_consent"}
        },
        "check_status": {},
    }

    def execute(name, function, *args):
        report(name, "RUNNING")
        try:
            result = function(*args)
            status = result.get("status", "PASSED") if isinstance(result, dict) else "PASSED"
            results["check_status"][name] = status
            results[name] = result
            report(name, status, result.get("reason", "") if isinstance(result, dict) else "")
        except Exception as exc:
            logger.exception("%s diagnostic failed", name)
            value = {"status": "FAILED", "reason": str(exc)}
            results["check_status"][name] = "FAILED"
            results[name] = value
            report(name, "FAILED", str(exc))

    report("network", "RUNNING")
    try:
        network = collect_network_info()
        results["network"] = network
        results["check_status"]["network"] = "PASSED" if network.get("adapters") else "WARNING"
        report("network", results["check_status"]["network"],
               f"{len(network.get('adapters', []))} adapters found.")
    except Exception as exc:
        logger.exception("Network information collection failed")
        network = {}
        results["network"] = {"status": "FAILED", "reason": str(exc)}
        results["check_status"]["network"] = "FAILED"
        report("network", "FAILED", str(exc))

    gateway = network.get("gateway")
    count = int(settings.get("ping_count", 20))
    timeout_ms = int(settings.get("ping_timeout_ms", 1500))
    max_hops = int(settings.get("traceroute_hops", 15))
    test_count = int(settings.get("speed_tests", 3))
    interval = int(settings.get("test_interval_seconds", 5))

    tasks = {
        "internet_connection": internet_connection,
        "dns": run_dns_diagnostics,
        "traceroute": run_traceroute,
        "speedtest": run_speedtests,
        "traffic": sample_traffic,
        "wifi": _wifi_diagnostics,
        "lan_iperf": run_iperf_test,
    }
    if gateway:
        tasks["gateway_ping"] = ping_host
    else:
        results["gateway_ping"] = {"status": "NOT AVAILABLE", "reason": "No default gateway detected."}
        results["check_status"]["gateway_ping"] = "NOT AVAILABLE"
        report("gateway_ping", "NOT AVAILABLE", "No default gateway detected.")
    for target in ("1.1.1.1", "8.8.8.8"):
        tasks[f"ping_{target.replace('.', '_')}"] = ping_host

    with concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="net-audit") as executor:
        future_map = {}
        for name, function in tasks.items():
            if name == "dns":
                args = (network.get("dns_servers", []),)
            elif name == "traceroute":
                args = ("1.1.1.1", max_hops, cancel_event)
            elif name == "speedtest":
                args = (test_count, interval, bool(settings.get("speedtest_consent")), cancel_event)
            elif name == "traffic":
                args = (min(5.0, max(1.0, interval)), cancel_event)
            elif name == "lan_iperf":
                args = (str(settings.get("lan_iperf_host", "")), False, cancel_event)
            elif name == "gateway_ping":
                args = (gateway, count, timeout_ms, cancel_event)
            elif name.startswith("ping_"):
                args = (name[5:].replace("_", "."), min(count, 5), timeout_ms, cancel_event)
            else:
                args = ()
            report(name, "RUNNING")
            future_map[executor.submit(function, *args)] = name
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                value = future.result()
            except Exception as exc:
                logger.exception("%s diagnostic task failed", name)
                value = {"status": "FAILED", "reason": str(exc)}
            results[name] = value
            status = value.get("status", "PASSED") if isinstance(value, dict) else "PASSED"
            results["check_status"][name] = status
            report(name, status, value.get("reason", "") if isinstance(value, dict) else "")

    if cancel_event.is_set():
        results["check_status"]["audit"] = "CANCELLED"
        results["status"] = "CANCELLED"
    else:
        tests = results.get("speedtest", {}).get("tests", [])
        summary = summarize_speed_tests(
            (item["download_mbps"] for item in tests if item.get("download_mbps") is not None),
            (item["upload_mbps"] for item in tests if item.get("upload_mbps") is not None),
        )
        results["speed_summary"] = summary
        thresholds = {
            key: float(settings.get(key, default))
            for key, default in (("threshold_good", 90), ("threshold_warning", 70), ("threshold_poor", 40))
        }
        results["download_compliance"] = analyze_package(
            summary["download_average_mbps"], settings.get("download_package_mbps"), thresholds
        )
        results["upload_compliance"] = analyze_package(
            summary["upload_average_mbps"], settings.get("upload_package_mbps"), thresholds
        )
        results["findings"] = analyze_findings(results, settings)
        statuses = results["check_status"].values()
        results["status"] = (
            "WARNING" if any(item in {"FAILED", "WARNING", "NOT AVAILABLE", "SKIPPED", "NOT TESTED"}
                             for item in statuses) else "PASSED"
        )
    results["finished_at"] = datetime.now(timezone.utc).isoformat()
    speed_avg = results.get("speed_summary", {}).get("download_average_mbps")
    if speed_avg is not None:
        results["executive_summary"] = (
            f"Average download was {speed_avg:.2f} Mbps against a configured "
            f"{settings.get('download_package_mbps', 0):.2f} Mbps download package. "
            f"Overall audit status: {results['status']}."
        )
    else:
        results["executive_summary"] = (
            "The audit completed without a verified speed-test measurement. "
            "Review individual check statuses and reasons."
        )
    return results
