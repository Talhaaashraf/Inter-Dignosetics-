"""SQLite storage for local diagnostic sessions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class DiagnosticDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, "
                "status TEXT NOT NULL, download_mbps REAL, upload_mbps REAL, "
                "latency_ms REAL, packet_loss_percent REAL, compliance_percent REAL, "
                "results_json TEXT NOT NULL)"
            )

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def save_session(self, results: dict) -> int:
        speed = results.get("speedtest", {})
        tests = speed.get("tests", [])
        downloads = [item["download_mbps"] for item in tests if item.get("download_mbps") is not None]
        uploads = [item["upload_mbps"] for item in tests if item.get("upload_mbps") is not None]
        ping = results.get("gateway_ping", {})
        compliance = results.get("download_compliance", {}).get("compliance_percent")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO sessions(created_at,status,download_mbps,upload_mbps,latency_ms,"
                "packet_loss_percent,compliance_percent,results_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    results.get("status", "UNKNOWN"),
                    sum(downloads) / len(downloads) if downloads else None,
                    sum(uploads) / len(uploads) if uploads else None,
                    ping.get("average_ms"),
                    ping.get("packet_loss_percent"),
                    compliance,
                    json.dumps(results, ensure_ascii=False, allow_nan=False),
                ),
            )
            return int(cursor.lastrowid)

    def list_sessions(self, limit: int = 500) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,status,download_mbps,upload_mbps,latency_ms,"
                "packet_loss_percent,compliance_percent FROM sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["results"] = json.loads(result.pop("results_json"))
        return result

    def purge_older_than(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE created_at < ?",
                (datetime.fromtimestamp(cutoff, timezone.utc).isoformat(),),
            )
            return cursor.rowcount
