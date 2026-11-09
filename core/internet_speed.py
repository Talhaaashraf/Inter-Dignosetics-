"""Official Ookla Speedtest CLI discovery, consent, and JSON parsing."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from threading import Event

from core.package_compliance import bytes_per_second_to_mbps
from core.process import CommandCancelled, run_command


class SpeedtestUnavailable(RuntimeError):
    pass


def find_speedtest() -> str | None:
    for command in ("speedtest.exe", "speedtest"):
        found = shutil.which(command)
        if found:
            return found
    candidates = [
        Path.home() / "AppData/Local/Programs/Speedtest/speedtest.exe",
        Path("C:/Program Files/Speedtest/speedtest.exe"),
        Path("C:/Program Files (x86)/Speedtest/speedtest.exe"),
    ]
    return next((str(path) for path in candidates if path.is_file()), None)


def speedtest_capabilities(executable: str) -> dict:
    version = run_command([executable, "--version"], 8)
    help_result = run_command([executable, "--help"], 8)
    return {
        "version": version.stdout.strip() or version.stderr.strip(),
        "help": help_result.stdout + help_result.stderr,
        "json_supported": "--format" in help_result.stdout + help_result.stderr,
    }


def _measurement(obj: dict, key: str) -> float | None:
    section = obj.get(key)
    if not isinstance(section, dict):
        return None
    value = section.get("bandwidth")
    if isinstance(value, (int, float)):
        return bytes_per_second_to_mbps(float(value))
    for field in ("bps", "bitsPerSecond", "bytesPerSecond"):
        value = section.get(field)
        if isinstance(value, (int, float)):
            return float(value) / (1_000_000 if field != "bytesPerSecond" else 125_000)
    return None


def parse_speedtest_json(output: str) -> dict:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Speedtest returned invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("Speedtest JSON must be an object.")
    ping = data.get("ping") if isinstance(data.get("ping"), dict) else {}
    server = data.get("server") if isinstance(data.get("server"), dict) else {}
    download = _measurement(data, "download")
    upload = _measurement(data, "upload")
    if download is None and upload is None:
        raise ValueError("Speedtest JSON did not contain download or upload bandwidth.")
    return {
        "download_mbps": download,
        "upload_mbps": upload,
        "ping_ms": ping.get("latency"),
        "idle_latency_ms": ping.get("low"),
        "jitter_ms": ping.get("jitter"),
        "packet_loss_percent": data.get("packetLoss"),
        "server": server.get("name"),
        "server_location": server.get("location"),
        "duration_seconds": data.get("testDuration"),
        "result_url": data.get("result", {}).get("url") if isinstance(data.get("result"), dict) else None,
        "raw": data,
    }


def run_speedtests(count: int, interval_seconds: int, consent: bool,
                   cancel_event: Event, progress=None) -> dict:
    executable = find_speedtest()
    if not executable:
        return {
            "status": "NOT AVAILABLE",
            "reason": "Official Ookla Speedtest CLI was not found. Install it from https://www.speedtest.net/apps/cli.",
            "tests": [],
        }
    if not consent:
        return {"status": "SKIPPED", "reason": "Ookla license/data-consent was not accepted.", "tests": []}
    results = []
    try:
        capabilities = speedtest_capabilities(executable)
        if not capabilities["json_supported"]:
            return {"status": "NOT AVAILABLE", "reason": "Installed Ookla CLI does not advertise JSON output support.", "tests": [], "capabilities": capabilities}
        for index in range(count):
            if cancel_event.is_set():
                raise CommandCancelled("Speed test was cancelled.")
            started = time.monotonic()
            result = run_command(
                [executable, "--format=json", "--accept-license", "--accept-gdpr"],
                timeout=150, cancel_event=cancel_event,
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or f"Speedtest exited with code {result.returncode}.")
            measured = parse_speedtest_json(result.stdout)
            measured["duration_seconds"] = measured["duration_seconds"] or time.monotonic() - started
            results.append(measured)
            if progress:
                progress(index + 1, count, measured)
            if index < count - 1:
                for _ in range(interval_seconds * 10):
                    if cancel_event.is_set():
                        raise CommandCancelled("Speed test was cancelled.")
                    time.sleep(0.1)
        return {"status": "PASSED", "tests": results, "capabilities": capabilities}
    except CommandCancelled:
        return {"status": "CANCELLED", "reason": "Speed test cancelled by the user.", "tests": results}
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        return {"status": "FAILED", "reason": str(exc), "tests": results}
