"""
Shared persistent registry for reusable tool candidates.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SharedToolRegistry:
    def __init__(self, path: str = ".dwc/memory/shared_tool_registry.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        if self.path.exists():
            return
        payload = {"version": 1, "entries": []}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def record_contribution(
        self,
        *,
        subtask_description: str,
        tool_name: str,
        tool_code: str,
        sample_input: Dict[str, Any],
        origin: str,
        contributor: str,
        success: bool,
        error_text: Optional[str],
        created_at: Optional[str] = None,
    ) -> None:
        payload = self._load()
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            entries = []

        code_hash = hashlib.sha256(tool_code.encode("utf-8")).hexdigest()
        now = created_at or datetime.now(timezone.utc).isoformat()
        target = self._find_entry(entries, code_hash)
        if target is None:
            target = {
                "code_hash": code_hash,
                "tool_name": tool_name,
                "origin": origin,
                "code": tool_code,
                "sample_input": sample_input,
                "description_samples": [],
                "contributors": [],
                "success_count": 0,
                "failure_count": 0,
                "last_error": "",
                "created_at": now,
                "updated_at": now,
            }
            entries.append(target)

        target["tool_name"] = tool_name
        target["origin"] = origin
        target["code"] = tool_code
        target["sample_input"] = sample_input if isinstance(sample_input, dict) else {}
        target["updated_at"] = now

        samples = target.get("description_samples")
        if not isinstance(samples, list):
            samples = []
        description = str(subtask_description).strip()
        if description and description not in samples:
            samples.append(description)
        target["description_samples"] = samples[-20:]

        contributors = target.get("contributors")
        if not isinstance(contributors, list):
            contributors = []
        contributor_name = str(contributor).strip()
        if contributor_name and contributor_name not in contributors:
            contributors.append(contributor_name)
        target["contributors"] = contributors

        can_learn_description = (
            contributor_name != "shared_tool_registry" and str(origin).strip() != "shared_registry"
        )
        target["success_count"] = int(target.get("success_count", 0))
        target["failure_count"] = int(target.get("failure_count", 0))
        if not can_learn_description:
            # Avoid feedback-loop drift where reused tools self-reinforce unrelated intents.
            target["description_samples"] = [
                sample
                for sample in target.get("description_samples", [])
                if str(sample).strip() != description
            ]
        if success:
            target["success_count"] += 1
        else:
            target["failure_count"] += 1
            target["last_error"] = (error_text or "").strip()[:500]

        entries.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
        payload["entries"] = entries[:500]
        self._save(payload)

    def suggest_tool(
        self,
        *,
        subtask_description: str,
    ) -> Optional[Dict[str, Any]]:
        payload = self._load()
        entries = payload.get("entries", [])
        if not isinstance(entries, list) or not entries:
            return None

        query_tokens = self._token_set(subtask_description)
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for entry in entries:
            success_count = int(entry.get("success_count", 0))
            if success_count <= 0:
                continue
            failure_count = int(entry.get("failure_count", 0))
            sample_tokens = self._entry_tokens(entry)
            similarity = self._jaccard_similarity(query_tokens, sample_tokens)
            reliability = success_count / max(1, success_count + failure_count)
            score = (0.75 * similarity) + (0.25 * reliability)
            if score > best_score:
                best_score = score
                best = dict(entry)

        if best is None:
            return None
        if best_score <= 0:
            return None
        best["similarity"] = round(best_score, 6)
        return best

    @staticmethod
    def _find_entry(entries: List[Dict[str, Any]], code_hash: str) -> Optional[Dict[str, Any]]:
        for entry in entries:
            if str(entry.get("code_hash")) == code_hash:
                return entry
        return None

    @staticmethod
    def _token_set(text: str) -> set:
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_]+", str(text).lower())
            if len(token) >= 3
        }

    def _entry_tokens(self, entry: Dict[str, Any]) -> set:
        values = []
        samples = entry.get("description_samples")
        if isinstance(samples, list):
            values.extend(str(sample) for sample in samples)
        values.append(str(entry.get("tool_name", "")))
        values.append(str(entry.get("origin", "")))
        merged = " ".join(values)
        return self._token_set(merged)

    @staticmethod
    def _jaccard_similarity(left: set, right: set) -> float:
        if not left or not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return float(len(left & right) / len(union))

    def _load(self) -> Dict[str, Any]:
        self._ensure_initialized()
        try:
            raw = self.path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception:
            payload = {"version": 1, "entries": []}
        if not isinstance(payload, dict):
            payload = {"version": 1, "entries": []}
        payload.setdefault("version", 1)
        payload.setdefault("entries", [])
        return payload

    def _save(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
