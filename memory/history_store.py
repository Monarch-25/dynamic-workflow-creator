"""
Persistent workflow execution history.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class HistoryStore:
    def __init__(self, db_path: str = ".dwc/memory/history.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    cost_estimate REAL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add_record(
        self,
        *,
        workflow_name: str,
        version: str,
        status: str,
        latency_ms: int,
        cost_estimate: Optional[float],
        created_at: str,
        payload: Dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflow_history (
                    workflow_name,
                    version,
                    status,
                    latency_ms,
                    cost_estimate,
                    created_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_name,
                    version,
                    status,
                    int(latency_ms),
                    cost_estimate,
                    created_at,
                    json.dumps(payload, sort_keys=True),
                ),
            )
            conn.commit()

    def recent(self, workflow_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_name, version, status, latency_ms, cost_estimate, created_at, payload_json
                FROM workflow_history
                WHERE workflow_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (workflow_name, limit),
            ).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "workflow_name": row[0],
                    "version": row[1],
                    "status": row[2],
                    "latency_ms": row[3],
                    "cost_estimate": row[4],
                    "created_at": row[5],
                    "payload": json.loads(row[6]),
                }
            )
        return results

    def failures(self, workflow_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_name, version, status, latency_ms, cost_estimate, created_at, payload_json
                FROM workflow_history
                WHERE workflow_name = ? AND status != 'success'
                ORDER BY id DESC
                LIMIT ?
                """,
                (workflow_name, limit),
            ).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "workflow_name": row[0],
                    "version": row[1],
                    "status": row[2],
                    "latency_ms": row[3],
                    "cost_estimate": row[4],
                    "created_at": row[5],
                    "payload": json.loads(row[6]),
                }
            )
        return results
