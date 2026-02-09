"""
Persistent workflow execution history.
"""

from __future__ import annotations

import json
import re
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_name TEXT NOT NULL,
                    subtask_id TEXT NOT NULL,
                    subtask_description TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_origin TEXT NOT NULL,
                    attempt_index INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    error_class TEXT,
                    stderr_snippet TEXT,
                    stdout_snippet TEXT,
                    feedback_used TEXT,
                    code_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tool_attempts_workflow
                ON tool_attempts(workflow_name, id DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tool_attempts_success
                ON tool_attempts(success, id DESC)
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

    def add_tool_attempt(
        self,
        *,
        workflow_name: str,
        subtask_id: str,
        subtask_description: str,
        tool_name: str,
        tool_origin: str,
        attempt_index: int,
        success: bool,
        error_class: Optional[str],
        stderr_snippet: Optional[str],
        stdout_snippet: Optional[str],
        feedback_used: Optional[str],
        code_hash: str,
        created_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_attempts (
                    workflow_name,
                    subtask_id,
                    subtask_description,
                    tool_name,
                    tool_origin,
                    attempt_index,
                    success,
                    error_class,
                    stderr_snippet,
                    stdout_snippet,
                    feedback_used,
                    code_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_name,
                    subtask_id,
                    subtask_description,
                    tool_name,
                    tool_origin,
                    int(attempt_index),
                    1 if success else 0,
                    error_class,
                    stderr_snippet,
                    stdout_snippet,
                    feedback_used,
                    code_hash,
                    created_at,
                ),
            )
            conn.commit()

    def recent_tool_attempts(
        self,
        *,
        workflow_name: Optional[str] = None,
        limit: int = 50,
        failures_only: bool = False,
    ) -> List[Dict[str, Any]]:
        where_clauses: List[str] = []
        params: List[Any] = []

        if workflow_name:
            where_clauses.append("workflow_name = ?")
            params.append(workflow_name)
        if failures_only:
            where_clauses.append("success = 0")

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    workflow_name,
                    subtask_id,
                    subtask_description,
                    tool_name,
                    tool_origin,
                    attempt_index,
                    success,
                    error_class,
                    stderr_snippet,
                    stdout_snippet,
                    feedback_used,
                    code_hash,
                    created_at
                FROM tool_attempts
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()

        return [
            {
                "workflow_name": row[0],
                "subtask_id": row[1],
                "subtask_description": row[2],
                "tool_name": row[3],
                "tool_origin": row[4],
                "attempt_index": row[5],
                "success": bool(row[6]),
                "error_class": row[7],
                "stderr_snippet": row[8],
                "stdout_snippet": row[9],
                "feedback_used": row[10],
                "code_hash": row[11],
                "created_at": row[12],
            }
            for row in rows
        ]

    def similar_failed_attempts(
        self,
        *,
        subtask_description: str,
        limit: int = 3,
        candidate_pool: int = 200,
    ) -> List[Dict[str, Any]]:
        candidates = self.recent_tool_attempts(
            workflow_name=None,
            limit=max(limit, candidate_pool),
            failures_only=True,
        )
        if not candidates:
            return []

        query_tokens = self._token_set(subtask_description)
        scored: List[Dict[str, Any]] = []
        for row in candidates:
            description = str(row.get("subtask_description", ""))
            target_tokens = self._token_set(description)
            score = self._jaccard_similarity(query_tokens, target_tokens)
            if score <= 0:
                continue
            enriched = dict(row)
            enriched["similarity"] = round(score, 6)
            scored.append(enriched)

        if not scored:
            return candidates[:limit]

        scored.sort(
            key=lambda item: (
                float(item.get("similarity", 0.0)),
                str(item.get("created_at", "")),
            ),
            reverse=True,
        )
        return scored[:limit]

    @staticmethod
    def _token_set(text: str) -> set:
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
            if len(token) >= 3
        }

    @staticmethod
    def _jaccard_similarity(left: set, right: set) -> float:
        if not left or not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return float(len(left & right) / len(union))
