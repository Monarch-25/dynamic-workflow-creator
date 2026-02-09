"""
Structured telemetry for workflow compilation and execution.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    trace_id: str
    event: str
    timestamp: str
    data: Dict[str, Any] = Field(default_factory=dict)


class TelemetryCollector:
    def __init__(self, root_dir: str = ".dwc/telemetry") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._events: Dict[str, List[TelemetryEvent]] = {}
        self._lock = threading.Lock()

    def start_trace(self, workflow_name: str) -> str:
        trace_id = f"{workflow_name}-{uuid.uuid4()}"
        with self._lock:
            self._events.setdefault(trace_id, [])
        self.log(trace_id, "trace_started", workflow_name=workflow_name)
        return trace_id

    def log(self, trace_id: str, event: str, **data: Any) -> TelemetryEvent:
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = TelemetryEvent(
            trace_id=trace_id, event=event, timestamp=timestamp, data=data
        )
        with self._lock:
            self._events.setdefault(trace_id, []).append(payload)
            self._append_to_disk(payload)
        return payload

    def events(self, trace_id: str) -> List[TelemetryEvent]:
        with self._lock:
            return list(self._events.get(trace_id, []))

    def summarize(self, trace_id: str) -> Dict[str, Any]:
        events = self.events(trace_id)
        return {
            "trace_id": trace_id,
            "event_count": len(events),
            "events": [
                item.model_dump() if hasattr(item, "model_dump") else item.dict()
                for item in events
            ],
        }

    def _append_to_disk(self, event: TelemetryEvent) -> None:
        path = self.root_dir / f"{event.trace_id}.jsonl"
        payload = event.model_dump() if hasattr(event, "model_dump") else event.dict()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
