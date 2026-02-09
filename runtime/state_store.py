"""
Execution state store for short-term orchestration state.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ExecutionState(BaseModel):
    trace_id: str
    workflow_name: str
    status: str = "created"
    iteration: int = 0
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    payload: Dict[str, Any] = Field(default_factory=dict)


class InMemoryStateStore:
    def __init__(self) -> None:
        self._store: Dict[str, ExecutionState] = {}
        self._lock = threading.Lock()

    def set(self, state: ExecutionState) -> None:
        with self._lock:
            self._store[state.trace_id] = state

    def get(self, trace_id: str) -> Optional[ExecutionState]:
        with self._lock:
            return self._store.get(trace_id)

    def update(
        self,
        trace_id: str,
        *,
        status: Optional[str] = None,
        iteration: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[ExecutionState]:
        with self._lock:
            state = self._store.get(trace_id)
            if not state:
                return None
            if status is not None:
                state.status = status
            if iteration is not None:
                state.iteration = iteration
            if payload is not None:
                state.payload = payload
            state.updated_at = datetime.now(timezone.utc).isoformat()
            self._store[trace_id] = state
            return state
