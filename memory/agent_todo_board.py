"""
Shared agent to-do board with live progress updates.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class TodoItem:
    key: str
    title: str
    status: str = "pending"
    checks: List[str] = field(default_factory=list)
    updated_at: str = ""


class AgentTodoBoard:
    STATUS_ICON = {
        "pending": "[ ]",
        "in_progress": "[~]",
        "completed": "[x]",
        "failed": "[!]",
    }

    def __init__(
        self,
        *,
        root_dir: str = ".dwc/memory_md",
        emit_console: Optional[bool] = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.agent_dir = self.root_dir / "agents"
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.agent_dir / "todo_board.md"
        self.emit_console = bool(sys.stdout.isatty()) if emit_console is None else emit_console
        self._items: Dict[str, Dict[str, TodoItem]] = {}
        self._order: List[str] = []
        self._run_label = "workflow"
        self._write()

    def begin_run(self, run_label: str) -> None:
        self._run_label = str(run_label or "workflow").strip() or "workflow"
        self._items = {}
        self._order = []
        self._write()

    def seed_agent(self, agent_name: str, items: Iterable[Tuple[str, str]]) -> None:
        agent = self._safe_name(agent_name)
        bucket = self._items.setdefault(agent, {})
        if agent not in self._order:
            self._order.append(agent)
        for key, title in items:
            safe_key = self._safe_name(key)
            if not safe_key:
                continue
            if safe_key not in bucket:
                bucket[safe_key] = TodoItem(
                    key=safe_key,
                    title=str(title).strip() or safe_key,
                    updated_at=self._timestamp(),
                )
        self._write()

    def start(self, agent_name: str, key: str, check: Optional[str] = None) -> None:
        self._update(agent_name, key, status="in_progress", check=check)

    def complete(self, agent_name: str, key: str, check: Optional[str] = None) -> None:
        self._update(agent_name, key, status="completed", check=check)

    def fail(self, agent_name: str, key: str, check: Optional[str] = None) -> None:
        self._update(agent_name, key, status="failed", check=check)

    def add_check(self, agent_name: str, key: str, check: str) -> None:
        self._update(agent_name, key, status=None, check=check)

    def _update(
        self,
        agent_name: str,
        key: str,
        *,
        status: Optional[str],
        check: Optional[str],
    ) -> None:
        agent = self._safe_name(agent_name)
        safe_key = self._safe_name(key)
        if not safe_key:
            return
        if agent not in self._items:
            self._items[agent] = {}
            self._order.append(agent)
        bucket = self._items[agent]
        item = bucket.get(safe_key)
        if item is None:
            item = TodoItem(
                key=safe_key,
                title=safe_key.replace("_", " "),
                updated_at=self._timestamp(),
            )
            bucket[safe_key] = item

        if status in self.STATUS_ICON:
            item.status = status
        message = str(check or "").strip()
        if message:
            item.checks.append(message)
        item.updated_at = self._timestamp()
        self._write()
        if self.emit_console:
            self._emit(agent=agent, item=item, message=message, status=status)

    def _emit(self, *, agent: str, item: TodoItem, message: str, status: Optional[str]) -> None:
        icon = self.STATUS_ICON.get(item.status, "[ ]")
        suffix = f" | {message}" if message else ""
        status_hint = f" -> {status}" if status else ""
        print(f"[todo] {agent}.{item.key} {icon}{status_hint}{suffix}")

    def _write(self) -> None:
        lines: List[str] = [
            "# Agent To-Do Board",
            "",
            f"_run: {self._run_label}_",
            f"_updated: {self._timestamp()}_",
            "",
        ]
        for agent in self._order:
            lines.append(f"## {agent}")
            bucket = self._items.get(agent, {})
            if not bucket:
                lines.append("- [ ] no tasks seeded")
                lines.append("")
                continue
            for key in sorted(bucket.keys()):
                item = bucket[key]
                icon = self.STATUS_ICON.get(item.status, "[ ]")
                lines.append(f"- {icon} `{item.key}`: {item.title}")
                if item.checks:
                    lines.append(f"  - latest: {item.checks[-1]}")
            lines.append("")
        self.path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(
            char if char.isalnum() or char in ("_", "-") else "_"
            for char in str(value).strip().lower()
        ).strip("_")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
