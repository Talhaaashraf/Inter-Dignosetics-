"""Adapter-level traffic counter sampling (does not identify applications)."""

from __future__ import annotations

import time
from threading import Event

import psutil


def sample_traffic(seconds: float = 2.0, cancel_event: Event | None = None) -> dict:
    before = psutil.net_io_counters(pernic=True)
    started = time.monotonic()
    if cancel_event is not None and cancel_event.wait(seconds):
        return {"status": "CANCELLED"}
    if cancel_event is None:
        time.sleep(seconds)
    elapsed = max(time.monotonic() - started, 0.001)
    after = psutil.net_io_counters(pernic=True)
    interfaces = {}
    for name, end in after.items():
        start = before.get(name)
        if start is None:
            continue
        received = max(0, end.bytes_recv - start.bytes_recv)
        sent = max(0, end.bytes_sent - start.bytes_sent)
        interfaces[name] = {
            "received_bytes": received, "sent_bytes": sent,
            "download_mbps": received * 8 / elapsed / 1_000_000,
            "upload_mbps": sent * 8 / elapsed / 1_000_000,
        }
    return {
        "status": "PASSED", "duration_seconds": elapsed, "interfaces": interfaces,
        "total_received_bytes": sum(item["received_bytes"] for item in interfaces.values()),
        "total_sent_bytes": sum(item["sent_bytes"] for item in interfaces.values()),
        "note": "Adapter counters aggregate all traffic and cannot attribute it to a process.",
    }
