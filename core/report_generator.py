"""Local HTML, JSON, and CSV report export with optional privacy redaction."""

from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path


def redact_data(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key.lower() in {"hostname", "macaddress", "ssid", "local_addresses", "public_ip"}:
                sanitized[key] = "[REDACTED]"
            elif key.lower() in {"mac", "mac_address", "ssid"}:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = redact_data(item)
        return sanitized
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP REDACTED]", value)
        value = re.sub(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", "[MAC REDACTED]", value)
    return value


def _flatten(value, prefix=""):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_flatten(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_flatten(item, f"{prefix}[{index}]"))
    else:
        rows.append((prefix, value))
    return rows


def export_report(results: dict, directory: str | Path, redact: bool = False) -> dict:
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    data = redact_data(results) if redact else results
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    json_path, html_path, csv_path = (output / f"diagnostic_report_{stamp}.{ext}" for ext in ("json", "html", "csv"))
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    rows = _flatten(data)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(("Metric", "Value"))
        writer.writerows(rows)
    findings = data.get("findings", [])
    summary = data.get("executive_summary", "Audit results are recorded below.")
    rendered = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>" for key, value in rows
    )
    finding_list = "".join(f"<li>{html.escape(item.get('title', 'Finding'))}: "
                           f"{html.escape(item.get('evidence', ''))}</li>" for item in findings)
    html_path.write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Network Diagnostic Report</title>"
        "<style>body{font:15px Segoe UI,sans-serif;max-width:1100px;margin:32px auto;color:#182230}"
        "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}"
        "tr:nth-child(even){background:#f5f7fa}</style><h1>ISP &amp; LAN Diagnostic Report</h1>"
        f"<p>{html.escape(str(summary))}</p><h2>Root cause analysis</h2><ul>{finding_list}</ul>"
        f"<h2>Full results</h2><table><tr><th>Metric</th><th>Value</th></tr>{rendered}</table></html>",
        encoding="utf-8",
    )
    return {"json": str(json_path), "html": str(html_path), "csv": str(csv_path)}
