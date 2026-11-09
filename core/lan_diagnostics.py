"""Optional iperf3 throughput tests for an explicitly supplied private LAN host."""

from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
from threading import Event

from core.process import CommandCancelled, run_command


def _validate_private_host(host: str) -> str:
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError as exc:
        raise ValueError("Enter a literal private LAN IP address for the iperf3 server.") from exc
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
        raise ValueError("iperf3 is limited to a private IPv4 LAN address.")
    return str(address)


def run_iperf_test(host: str, udp: bool = False, cancel_event: Event | None = None) -> dict:
    if not host.strip():
        return {"status": "NOT TESTED", "reason": "No authorized LAN iperf3 server address was supplied."}
    try:
        target = _validate_private_host(host)
    except ValueError as exc:
        return {"status": "SKIPPED", "reason": str(exc)}
    executable = shutil.which("iperf3.exe") or shutil.which("iperf3")
    if not executable:
        return {"status": "NOT AVAILABLE", "reason": "Install iperf3 and place iperf3.exe on PATH."}
    if udp:
        return {
            "status": "SKIPPED",
            "reason": "UDP throughput testing is deliberately disabled in this release to avoid unexpectedly sustained traffic.",
        }
    results = {}
    for label, direction_args in (("upload", []), ("download", ["-R"])):
        try:
            completed = run_command(
                [executable, "-c", target, "-J", "-t", "5", *direction_args],
                timeout=15, cancel_event=cancel_event,
            )
            if completed.returncode:
                results[label] = {"status": "FAILED", "reason": completed.stderr.strip() or "iperf3 failed."}
                continue
            data = json.loads(completed.stdout)
            end = data.get("end", {})
            stream = end.get("sum_received") or end.get("sum") or end.get("sum_sent") or {}
            results[label] = {
                "status": "PASSED",
                "mbps": stream.get("bits_per_second", 0) / 1_000_000,
                "bytes": stream.get("bytes"),
                "seconds": stream.get("seconds"),
            }
        except CommandCancelled:
            return {"status": "CANCELLED", "results": results}
        except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            results[label] = {"status": "FAILED", "reason": str(exc)}
    passed = any(item.get("status") == "PASSED" for item in results.values())
    return {
        "status": "PASSED" if passed else "FAILED",
        "server": target,
        "transport": "TCP",
        "results": results,
        "note": "Tests ran only against the explicitly supplied private LAN server.",
    }
