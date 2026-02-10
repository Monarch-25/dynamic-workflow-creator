"""
Session-aware path resolver for DWC persistence.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _safe_session_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip()).strip("._-")
    return cleaned or f"session_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class SessionPaths:
    dwc_root: Path
    session_mode: str
    session_id: str
    session_root: Path
    memory_md_dir: Path
    history_db_path: Path
    vector_store_path: Path
    telemetry_dir: Path
    sandboxes_dir: Path
    shared_tool_registry_path: Path


def resolve_session_paths(
    *,
    dwc_root: str = ".dwc",
    session_mode: str = "isolated",
    session_id: Optional[str] = None,
) -> SessionPaths:
    root = Path(dwc_root).expanduser().resolve()
    normalized_mode = str(session_mode or "isolated").strip().lower()
    if normalized_mode not in ("isolated", "shared"):
        raise ValueError("session_mode must be 'isolated' or 'shared'.")

    resolved_session_id = _safe_session_id(session_id or "")
    if normalized_mode == "shared":
        resolved_session_id = "shared"
        session_root = root
    else:
        session_root = root / "sessions" / resolved_session_id

    memory_dir = session_root / "memory"
    memory_md_dir = session_root / "memory_md"
    telemetry_dir = session_root / "telemetry"
    sandboxes_dir = session_root / "sandboxes"
    shared_tools_dir = root / "shared" / "tools"
    shared_registry_path = shared_tools_dir / "shared_tool_registry.json"

    # Ensure parent directories exist before stores/sandboxes initialize.
    root.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_md_dir.mkdir(parents=True, exist_ok=True)
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    sandboxes_dir.mkdir(parents=True, exist_ok=True)
    shared_tools_dir.mkdir(parents=True, exist_ok=True)

    return SessionPaths(
        dwc_root=root,
        session_mode=normalized_mode,
        session_id=resolved_session_id,
        session_root=session_root,
        memory_md_dir=memory_md_dir,
        history_db_path=memory_dir / "history.db",
        vector_store_path=memory_dir / "vector_store.jsonl",
        telemetry_dir=telemetry_dir,
        sandboxes_dir=sandboxes_dir,
        shared_tool_registry_path=shared_registry_path,
    )


def migrate_legacy_shared_tool_registry(paths: SessionPaths) -> None:
    if paths.shared_tool_registry_path.exists():
        return
    legacy_path = paths.dwc_root / "memory" / "shared_tool_registry.json"
    if not legacy_path.exists():
        return
    try:
        payload = legacy_path.read_text(encoding="utf-8")
    except Exception:
        return
    if not payload.strip():
        return
    paths.shared_tool_registry_path.write_text(payload, encoding="utf-8")

