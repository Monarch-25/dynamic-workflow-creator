"""Generated tool arsenal for workflow."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

import os
import shlex
import subprocess
import sys

BANNED_CLI_PATTERNS = (
    "rm ",
    "rm -",
    "shutil.rmtree",
    "os.remove",
    "mkfs",
    "shutdown",
    "reboot",
)

BLOCKED_SHELL_TOKENS = (
    "|",
    "&&",
    "||",
    ";",
    ">",
    "<",
    "$(",
    "`",
)

def _contains_blocked_tokens(command: str) -> bool:
    return any(token in command for token in BLOCKED_SHELL_TOKENS)

def _decision_from_user_message(user_message: str, command: str) -> Tuple[str, Optional[str]]:
    message = user_message.strip()
    lowered = message.lower()
    if lowered.startswith("modify:"):
        replacement = message.split(":", 1)[1].strip()
        if replacement:
            return "execute", replacement
    if lowered.startswith("replace with "):
        replacement = message[len('replace with '):].strip()
        if replacement:
            return "execute", replacement
    if any(token in lowered for token in (
        "execute", "run", "yes", "approve", "proceed", "continue"
    )):
        return "execute", command
    if any(token in lowered for token in (
        "skip", "no", "deny", "block", "cancel", "stop", "other", "something else"
    )):
        return "skip", None
    return "skip", None

def _prompt_shell_decision(command: str) -> Tuple[str, Optional[str]]:
    print("[safe_cli] Pending shell command:")
    print(f"[safe_cli]   {command}")
    print("[safe_cli] Reply: execute | modify:<new command> | skip")
    user_message = input("[safe_cli] > ").strip()
    return _decision_from_user_message(user_message, command)

def _resolve_shell_command(command: str, user_message: Optional[str] = None) -> Optional[str]:
    mode = os.getenv("DWC_SAFE_CLI_MODE", "prompt").strip().lower()
    if mode == "allow":
        return command
    if mode == "deny":
        return None
    seed_message = (user_message or "").strip()
    if not seed_message:
        seed_message = os.getenv("DWC_SAFE_CLI_USER_MESSAGE", "").strip()
    if seed_message:
        action, final_command = _decision_from_user_message(seed_message, command)
        if action == "execute" and final_command:
            return final_command
        return None
    if not sys.stdin.isatty():
        raise RuntimeError(
            "safe_cli requires interactive approval. Set DWC_SAFE_CLI_MODE=allow|deny or DWC_SAFE_CLI_USER_MESSAGE."
        )
    action, final_command = _prompt_shell_decision(command)
    if action == "execute" and final_command:
        return final_command
    return None

def safe_cli(command: str, user_message: Optional[str] = None) -> str:
    approved_command = _resolve_shell_command(command, user_message=user_message)
    if not approved_command:
        return "Command skipped by user approval policy."
    lower = approved_command.lower()
    if any(pattern in lower for pattern in BANNED_CLI_PATTERNS):
        raise ValueError("Blocked potentially harmful CLI command.")
    if _contains_blocked_tokens(approved_command):
        raise ValueError("Blocked shell meta-operators. Provide a direct argv-style command.")
    try:
        argv = shlex.split(approved_command)
    except ValueError as exc:
        raise ValueError(f"Unable to parse command: {exc}") from exc
    if not argv:
        raise ValueError("Empty CLI command after parsing.")
    result = subprocess.run(
        argv, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}

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
        return {}
    path_s, line_s, column_s, preview = parts
    try:
        line_no = int(line_s)
        column_no = int(column_s)
    except ValueError:
        return {}
    return {
        "path": path_s,
        "line": line_no,
        "column": column_no,
        "preview": preview.strip(),
    }


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
                    {
                        "path": rel_path,
                        "line": line_no,
                        "column": int(found.start()) + 1,
                        "preview": line.strip(),
                    }
                )
    return {
        "matches": matches,
        "total_matches": total_matches,
    }


def tool_task_1(task_input: Dict[str, Any]) -> Dict[str, Any]:
    raw_pattern = task_input.get("pattern") or task_input.get("query") or ""
    pattern = str(raw_pattern).strip()
    if not pattern:
        payload = {
            "engine": "none",
            "error": "Missing 'pattern' (or query) for code search.",
            "matches": [],
            "total_matches": 0,
        }
        return {
            "tool": "tool_task_1",
            "status": "ok",
            "result": json.dumps(payload, sort_keys=True),
        }

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
        payload = {
            "engine": "none",
            "error": f"Search root does not exist: {search_root}",
            "matches": [],
            "total_matches": 0,
        }
        return {
            "tool": "tool_task_1",
            "status": "ok",
            "result": json.dumps(payload, sort_keys=True),
        }

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
            payload = {
                "engine": "rg",
                "pattern": pattern,
                "glob": raw_glob,
                "root": str(search_root),
                "matches": matches,
                "total_matches": total_matches,
                "truncated": total_matches > len(matches),
            }
            return {
                "tool": "tool_task_1",
                "status": "ok",
                "result": json.dumps(payload, sort_keys=True),
            }

    fallback = _fallback_python_search(
        pattern=pattern,
        glob_pattern=raw_glob,
        search_root=search_root,
        workspace_root=workspace_root,
        max_results=max_results,
    )
    payload = {
        "engine": "python_fallback",
        "pattern": pattern,
        "glob": raw_glob,
        "root": str(search_root),
        "matches": fallback["matches"],
        "total_matches": fallback["total_matches"],
        "truncated": fallback["total_matches"] > len(fallback["matches"]),
    }
    return {
        "tool": "tool_task_1",
        "status": "ok",
        "result": json.dumps(payload, sort_keys=True),
    }


TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "tool_task_1": tool_task_1,
}
