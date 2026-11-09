"""Limited Windows traceroute analysis."""

from __future__ import annotations

import re
import shutil
import subprocess
from threading import Event

from core.process import CommandCancelled, run_command

_HOP = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_TIME = re.compile(r"(\d+)\s*ms|<1\s*ms", re.I)


def parse_traceroute(output: str) -> list[dict]:
    hops = []
    for line in output.splitlines():
        match = _HOP.match(line)
        if not match:
            continue
        number, detail = int(match.group(1)), match.group(2)
        if number > 64:
            continue
        ip_match = _IP.search(detail)
        times = [float(item.group(1)) if item.group(1) else 0.5 for item in _TIME.finditer(detail)]
        hops.append({
            "hop": number,
            "ip": ip_match.group(0) if ip_match else None,
            "hostname": detail[:ip_match.start()].strip() if ip_match else None,
            "response_times_ms": times,
            "average_ms": sum(times) / len(times) if times else None,
            "timed_out": "*" in detail or not times,
            "detail": detail,
        })
    return hops


def run_traceroute(destination: str, max_hops: int, cancel_event: Event) -> dict:
    executable = shutil.which("tracert.exe") or shutil.which("tracert")
    if not executable:
        return {"status": "NOT AVAILABLE", "reason": "Windows tracert executable not found.", "hops": []}
    try:
        result = run_command([executable, "-d", "-h", str(max_hops), "-w", "700", destination],
                             timeout=max(20, max_hops * 2.5), cancel_event=cancel_event)
        hops = parse_traceroute(result.stdout + "\n" + result.stderr)
        return {
            "status": "PASSED" if hops else "WARNING",
            "destination": destination, "hops": hops,
            "note": "Intermediate routers may not answer ICMP and can still forward traffic normally.",
            "reason": None if hops else "No hops were parsed from Windows tracert output.",
        }
    except CommandCancelled:
        return {"status": "CANCELLED", "hops": []}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "FAILED", "reason": str(exc), "hops": []}
