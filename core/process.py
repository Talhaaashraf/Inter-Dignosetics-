"""Safe subprocess helpers for read-only Windows diagnostics."""

from __future__ import annotations

import subprocess
import time
from threading import Event


class CommandCancelled(Exception):
    """Raised when a diagnostic command is cancelled."""


def run_command(args: list[str], timeout: float, cancel_event: Event | None = None,
                input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run an executable without a shell, with timeout and cancellation support."""
    process = subprocess.Popen(
        args, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    if input_text is not None and process.stdin is not None:
        process.stdin.write(input_text)
        process.stdin.close()
    started = time.monotonic()
    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            process.kill()
            process.communicate()
            raise CommandCancelled("Diagnostic was cancelled.")
        if time.monotonic() - started > timeout:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
        time.sleep(0.1)
    stdout, stderr = process.communicate()
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
