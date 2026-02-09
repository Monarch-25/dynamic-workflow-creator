"""
Markdown-based shared and working memory store.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class MarkdownMemoryStore:
    """
    Memory layout:
      .dwc/memory_md/current_task_description.md
      .dwc/memory_md/agents/<agent_name>.md
    """

    def __init__(self, root_dir: str = ".dwc/memory_md") -> None:
        self.root_dir = Path(root_dir)
        self.agent_dir = self.root_dir / "agents"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.current_task_path = self.root_dir / "current_task_description.md"

    def set_current_task_description(self, text: str) -> None:
        timestamp = self._timestamp()
        body = (
            "# Current Task Description\n\n"
            f"_updated: {timestamp}_\n\n"
            f"{text.strip()}\n"
        )
        self.current_task_path.write_text(body, encoding="utf-8")

    def read_current_task_description(self) -> str:
        if not self.current_task_path.exists():
            return ""
        return self.current_task_path.read_text(encoding="utf-8")

    def append_agent_working_memory(self, agent_name: str, note: str) -> None:
        safe_name = self._safe_name(agent_name)
        path = self.agent_dir / f"{safe_name}.md"
        if not path.exists():
            header = f"# Working Memory: {agent_name}\n\n"
            path.write_text(header, encoding="utf-8")

        entry = (
            f"## {self._timestamp()}\n\n"
            f"{note.strip()}\n\n"
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def read_agent_working_memory(self, agent_name: str) -> str:
        path = self.agent_dir / f"{self._safe_name(agent_name)}.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def export_snapshot(self, destination_dir: str) -> None:
        """
        Copy current task and all agent memory files into destination.
        """

        dst_root = Path(destination_dir) / "memory"
        dst_agents = dst_root / "agents"
        dst_agents.mkdir(parents=True, exist_ok=True)

        if self.current_task_path.exists():
            (dst_root / "current_task_description.md").write_text(
                self.current_task_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        for path in self.agent_dir.glob("*.md"):
            (dst_agents / path.name).write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8"
            )

    @staticmethod
    def _safe_name(agent_name: str) -> str:
        return "".join(
            char if char.isalnum() or char in ("_", "-") else "_"
            for char in agent_name.strip().lower()
        ) or "agent"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

