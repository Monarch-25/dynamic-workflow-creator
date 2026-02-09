"""
Versioning and rollback support for stable workflow artifacts.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from dwc.ir.spec_schema import WorkflowSpec, model_dump_compat

SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(version: str) -> Tuple[int, int, int]:
    match = SEMVER_PATTERN.match(version.strip())
    if not match:
        raise ValueError(f"Invalid semantic version: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_semver(version: str, part: str = "patch") -> str:
    major, minor, patch = parse_semver(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown version part '{part}'. Use major/minor/patch.")


def normalize_workflow_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    return sanitized or "workflow"


class VersionRecord(BaseModel):
    workflow_name: str
    version: str
    created_at: str
    spec: Dict[str, Any]
    optimized_spec: Dict[str, Any]
    generated_code_path: str
    performance: Dict[str, Any] = Field(default_factory=dict)


class WorkflowVersionManager:
    """
    JSON-backed version registry.

    Stored at:
      .dwc/versions/<workflow_name>.json
    """

    def __init__(self, root_dir: str = ".dwc/versions") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _registry_path(self, workflow_name: str) -> Path:
        safe_name = normalize_workflow_name(workflow_name)
        return self.root_dir / f"{safe_name}.json"

    def list_versions(self, workflow_name: str) -> List[VersionRecord]:
        path = self._registry_path(workflow_name)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = [VersionRecord(**row) for row in raw]
        return sorted(records, key=lambda item: parse_semver(item.version))

    def latest_version(self, workflow_name: str) -> Optional[str]:
        records = self.list_versions(workflow_name)
        if not records:
            return None
        return records[-1].version

    def next_version(self, workflow_name: str, part: str = "patch") -> str:
        latest = self.latest_version(workflow_name)
        if latest is None:
            return "1.0.0"
        return bump_semver(latest, part=part)

    def register_stable_version(
        self,
        *,
        workflow_name: str,
        spec: WorkflowSpec,
        optimized_spec: WorkflowSpec,
        generated_code_path: str,
        performance: Optional[Dict[str, Any]] = None,
        bump_part: str = "patch",
    ) -> VersionRecord:
        versions = self.list_versions(workflow_name)
        version = self.next_version(workflow_name, part=bump_part)
        now = datetime.now(timezone.utc).isoformat()
        record = VersionRecord(
            workflow_name=normalize_workflow_name(workflow_name),
            version=version,
            created_at=now,
            spec=model_dump_compat(spec),
            optimized_spec=model_dump_compat(optimized_spec),
            generated_code_path=generated_code_path,
            performance=performance or {},
        )
        versions.append(record)
        serialized = [row.model_dump() if hasattr(row, "model_dump") else row.dict() for row in versions]  # type: ignore[attr-defined]
        self._registry_path(workflow_name).write_text(
            json.dumps(serialized, indent=2, sort_keys=True), encoding="utf-8"
        )
        return record

    def rollback_to(self, workflow_name: str, version: str) -> VersionRecord:
        for item in self.list_versions(workflow_name):
            if item.version == version:
                return item
        raise ValueError(
            f"Version '{version}' not found for workflow '{workflow_name}'."
        )
