"""Gateway and public IP latency measurements using Windows ping."""

from __future__ import annotations

import re
import shutil
import subprocess
from statistics import mean
from threading import Event

from core.process import CommandCancelled, run_command

_RTT = re.compile(r"(?:time|time<)\s*([=<])?\s*(\d+)\s*ms", re.I)


def parse_ping_output(output: str) -> dict:
    times = [float(match.group(2)) for match in _RTT.finditer(output)]
    sent_match = re.search(r"Packets: Sent = (\d+), Received = (\d+), Lost = (\d+)", output, re.I)
    sent = int(sent_match.group(1)) if sent_match else len(times)
    received = int(sent_match.group(2)) if sent_match else len(times)
    rtts = re.search(r"Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms", output, re.I)
    loss = max(0, sent - received) / sent * 100 if sent else None
    jitter = sum(abs(b - a) for a, b in zip(times, times[1:])) / (len(times) - 1) if len(times) > 1 else None
    return {
        "sent": sent, "received": received, "failed": max(0, sent - received),
        "packet_loss_percent": loss, "latencies_ms": times,
        "average_ms": int(rtts.group(3)) if rtts else (mean(times) if times else None),
        "minimum_ms": int(rtts.group(1)) if rtts else (min(times) if times else None),
        "maximum_ms": int(rtts.group(2)) if rtts else (max(times) if times else None),
        "jitter_estimate_ms": jitter,
        "status": "PASSED" if times else "WARNING",
        "note": "No ICMP reply does not prove that internet access is unavailable.",
    }


def ping_host(host: str, count: int, timeout_ms: int, cancel_event: Event | None = None) -> dict:
    ping = shutil.which("ping.exe") or shutil.which("ping")
    if not ping:
        return {"host": host, "status": "NOT AVAILABLE", "reason": "Windows ping executable not found."}
    try:
        result = run_command([ping, "-n", str(count), "-w", str(timeout_ms), host],
                             timeout=max(10, (count * timeout_ms / 1000) + 5),
                             cancel_event=cancel_event)
        data = parse_ping_output(result.stdout + "\n" + result.stderr)
        data["host"] = host
        if not data["received"] and ("Destination host unreachable" in result.stdout or "Destination net unreachable" in result.stdout):
            data["status"] = "FAILED"
            data["reason"] = "Windows reported the destination unreachable."
        elif not data["received"]:
            data["status"] = "WARNING"
            data["reason"] = "No ICMP replies; ICMP may be filtered."
        return data
    except CommandCancelled:
        return {"host": host, "status": "CANCELLED"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"host": host, "status": "FAILED", "reason": str(exc)}
