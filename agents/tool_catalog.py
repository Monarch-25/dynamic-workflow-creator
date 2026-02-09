"""
Built-in deterministic tool catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Dict, Optional

from dwc.agents.subtask_agent import SubtaskSpec


@dataclass
class BuiltinToolCandidate:
    description: str
    code: str
    sample_input: Dict[str, Any]


class BuiltinToolCatalog:
    """
    Deterministic tools selected from subtask intent without LLM generation.
    """

    CODE_SEARCH_HINTS = (
        "grep",
        "ripgrep",
        "rg ",
        "search code",
        "search python",
        "find in code",
        "find in repo",
        "find references",
        "locate symbol",
        "scan files",
    )
    SHELL_COMMAND_HINTS = (
        "shell command",
        "terminal command",
        "command line",
        "bash command",
        "cli command",
        "run shell",
        "execute shell",
    )

    def resolve(
        self,
        *,
        subtask: SubtaskSpec,
        function_name: str,
    ) -> Optional[BuiltinToolCandidate]:
        lower = subtask.description.lower()
        if self._matches_code_search(lower):
            return BuiltinToolCandidate(
                description=subtask.description,
                code=self._code_search_tool(function_name),
                sample_input={
                    "pattern": r"def\s+[a-zA-Z_][a-zA-Z0-9_]*\(",
                    "glob": "*.py",
                    "root": ".",
                    "max_results": 10,
                },
            )
        if self._matches_shell_command(lower):
            return BuiltinToolCandidate(
                description=subtask.description,
                code=self._shell_command_tool(function_name),
                sample_input={
                    "command": "echo hello",
                    "user_message": "modify:echo approved-from-user",
                },
            )
        return None

    @classmethod
    def _matches_code_search(cls, lower_description: str) -> bool:
        if any(hint in lower_description for hint in cls.CODE_SEARCH_HINTS):
            return True
        if "python" in lower_description and any(
            token in lower_description for token in ("search", "find", "symbol", "reference")
        ):
            return True
        return False

    @classmethod
    def _matches_shell_command(cls, lower_description: str) -> bool:
        if any(hint in lower_description for hint in cls.SHELL_COMMAND_HINTS):
            return True
        if "shell" in lower_description and any(
            token in lower_description for token in ("command", "cli", "terminal", "approve")
        ):
            return True
        if "command" in lower_description and "user" in lower_description and any(
            token in lower_description for token in ("approve", "confirm", "modify")
        ):
            return True
        return False

    @staticmethod
    def _shell_command_tool(function_name: str) -> str:
        body = f"""
import json
from typing import Any, Dict

def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    raw_command = task_input.get("command") or task_input.get("query") or ""
    command = str(raw_command).strip()
    if not command:
        return {{
            "tool": "{function_name}",
            "status": "ok",
            "result": json.dumps({{
                "error": "Missing command. Pass task_input['command'].",
                "output": "",
            }}, sort_keys=True),
        }}

    user_message = task_input.get("user_message") or task_input.get("approval") or ""
    user_message = str(user_message).strip() or None

    output = safe_cli(command, user_message=user_message)
    payload = {{
        "command": command,
        "user_message": user_message or "",
        "output": output,
    }}
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": json.dumps(payload, sort_keys=True),
    }}
"""
        return dedent(body).strip() + "\n"

    @staticmethod
    def _code_search_tool(function_name: str) -> str:
        body = f"""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

EXCLUDED_DIR_NAMES = {{
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}}

EXCLUDED_GLOBS = (
    "!**/.git/**",
    "!**/.venv/**",
    "!**/venv/**",
    "!**/__pycache__/**",
    "!**/.mypy_cache/**",
    "!**/.pytest_cache/**",
)


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _parse_rg_line(line: str) -> Dict[str, Any]:
    parts = line.split(":", 3)
    if len(parts) != 4:
        return {{}}
    path_s, line_s, column_s, preview = parts
    try:
        line_no = int(line_s)
        column_no = int(column_s)
    except ValueError:
        return {{}}
    return {{
        "path": path_s,
        "line": line_no,
        "column": column_no,
        "preview": preview.strip(),
    }}


def _fallback_python_search(
    *,
    pattern: str,
    glob_pattern: str,
    search_root: Path,
    workspace_root: Path,
    max_results: int,
) -> Dict[str, Any]:
    try:
        pattern_re = re.compile(pattern)
    except re.error:
        pattern_re = re.compile(re.escape(pattern))

    try:
        files = sorted(search_root.rglob(glob_pattern))
    except Exception:
        files = sorted(search_root.rglob("*.py"))

    matches: List[Dict[str, Any]] = []
    total_matches = 0

    for path in files:
        if len(matches) >= max_results and total_matches > max_results:
            break
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if not _is_within(workspace_root, path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for found in pattern_re.finditer(line):
                total_matches += 1
                if len(matches) >= max_results:
                    continue
                try:
                    rel_path = str(path.resolve().relative_to(workspace_root.resolve()))
                except Exception:
                    rel_path = str(path)
                matches.append(
                    {{
                        "path": rel_path,
                        "line": line_no,
                        "column": int(found.start()) + 1,
                        "preview": line.strip(),
                    }}
                )
    return {{
        "matches": matches,
        "total_matches": total_matches,
    }}


def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    raw_pattern = task_input.get("pattern") or task_input.get("query") or ""
    pattern = str(raw_pattern).strip()
    if not pattern:
        payload = {{
            "engine": "none",
            "error": "Missing 'pattern' (or query) for code search.",
            "matches": [],
            "total_matches": 0,
        }}
        return {{
            "tool": "{function_name}",
            "status": "ok",
            "result": json.dumps(payload, sort_keys=True),
        }}

    raw_glob = str(task_input.get("glob") or "*.py").strip() or "*.py"
    max_results_raw = task_input.get("max_results", 50)
    try:
        max_results = max(1, min(int(max_results_raw), 200))
    except Exception:
        max_results = 50

    workspace_root = Path(str(task_input.get("workspace_root") or ".")).resolve()
    raw_root = str(task_input.get("root") or ".").strip() or "."
    root_path = Path(raw_root)
    if root_path.is_absolute():
        search_root = root_path.resolve()
    else:
        search_root = (workspace_root / root_path).resolve()

    if not _is_within(workspace_root, search_root):
        search_root = workspace_root

    if not search_root.exists():
        payload = {{
            "engine": "none",
            "error": f"Search root does not exist: {{search_root}}",
            "matches": [],
            "total_matches": 0,
        }}
        return {{
            "tool": "{function_name}",
            "status": "ok",
            "result": json.dumps(payload, sort_keys=True),
        }}

    rg_bin = shutil.which("rg")
    if rg_bin:
        command = [
            rg_bin,
            "--line-number",
            "--column",
            "--no-heading",
            "--color",
            "never",
            "--glob",
            raw_glob,
        ]
        for glob_rule in EXCLUDED_GLOBS:
            command.extend(["--glob", glob_rule])
        command.extend(["--", pattern, str(search_root)])
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode in (0, 1):
            matches: List[Dict[str, Any]] = []
            total_matches = 0
            for raw_line in completed.stdout.splitlines():
                row = _parse_rg_line(raw_line)
                if not row:
                    continue
                total_matches += 1
                if len(matches) >= max_results:
                    continue
                full_path = Path(str(row["path"])).resolve()
                if not _is_within(workspace_root, full_path):
                    continue
                try:
                    row["path"] = str(full_path.relative_to(workspace_root))
                except Exception:
                    row["path"] = str(full_path)
                matches.append(row)
            payload = {{
                "engine": "rg",
                "pattern": pattern,
                "glob": raw_glob,
                "root": str(search_root),
                "matches": matches,
                "total_matches": total_matches,
                "truncated": total_matches > len(matches),
            }}
            return {{
                "tool": "{function_name}",
                "status": "ok",
                "result": json.dumps(payload, sort_keys=True),
            }}

    fallback = _fallback_python_search(
        pattern=pattern,
        glob_pattern=raw_glob,
        search_root=search_root,
        workspace_root=workspace_root,
        max_results=max_results,
    )
    payload = {{
        "engine": "python_fallback",
        "pattern": pattern,
        "glob": raw_glob,
        "root": str(search_root),
        "matches": fallback["matches"],
        "total_matches": fallback["total_matches"],
        "truncated": fallback["total_matches"] > len(fallback["matches"]),
    }}
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": json.dumps(payload, sort_keys=True),
    }}
"""
        return dedent(body).strip() + "\n"
