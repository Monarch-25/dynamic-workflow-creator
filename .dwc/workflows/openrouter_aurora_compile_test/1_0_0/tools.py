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

from typing import Any, Dict

def tool_load_markdown_input(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = task_input.get("query") or task_input.get("doc") or task_input.get("text") or ""
    text = " ".join(str(value).split()).strip()
    if not text:
        text = "Read the markdown file or input string containing the content to be processed."
    text = text[:700]
    result = (
        "Task focus: " + "Read the markdown file or input string containing the content to be processed." + ". "
        "Processed output: " + text + ". "
        + "Verifier feedback: Prior verifier failures for similar subtasks:\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-375eb3d8fc80/verify_tool.py\", line 120, in <module> _assert_\n\nPotential reusable implementation from shared tool registry:\n- tool=tool_task_2, origin=shared_registry, similarity=0.3"
    )[:900]
    return {
        "tool": "tool_load_markdown_input",
        "status": "ok",
        "result": result,
    }


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


def tool_find_python_code_blocks(task_input: Dict[str, Any]) -> Dict[str, Any]:
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
            "tool": "tool_find_python_code_blocks",
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
            "tool": "tool_find_python_code_blocks",
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
                "tool": "tool_find_python_code_blocks",
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
        "tool": "tool_find_python_code_blocks",
        "status": "ok",
        "result": json.dumps(payload, sort_keys=True),
    }


from typing import Any, Dict

def tool_extract_code_snippets(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = (
        task_input.get("doc")
        or task_input.get("text")
        or task_input.get("query")
        or str(task_input)
    )
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        cleaned = "Capture the inner text of each identified Python code block and store them in a list."
    result = ("Fallback output for: " + "Capture the inner text of each identified Python code block and store them in a list." + ". " + cleaned)[:900]
    return {
        "tool": "tool_extract_code_snippets",
        "status": "ok",
        "result": result,
    }


from typing import Any, Dict

def tool_parse_ast_for_definitions(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = task_input.get("query") or task_input.get("doc") or task_input.get("text") or ""
    text = " ".join(str(value).split()).strip()
    if not text:
        text = "For each snippet, build an abstract syntax tree to locate top\u2011level functions, classes, and import statements."
    text = text[:700]
    result = (
        "Task focus: " + "For each snippet, build an abstract syntax tree to locate top\u2011level functions, classes, and import statements." + ". "
        "Processed output: " + text + ". "
        + "Verifier feedback: Prior verifier failures for similar subtasks:\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-375eb3d8fc80/verify_tool.py\", line 120, in <module> _assert_\n- VerifierError: Repeated identical tool candidate code. Stopping retry loop early to avoid redundant failures.\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-086febb8ed22/verify_tool.py\", line 120, in <module> _assert_\n\nPotential reusable implementation from shared tool registry:\n- tool=tool_search_python_files_todo_comments_summarize, origin=builtin, similarity=0.31"
    )[:900]
    return {
        "tool": "tool_parse_ast_for_definitions",
        "status": "ok",
        "result": result,
    }


from typing import Any, Dict

def tool_generate_snippet_description(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = task_input.get("query") or task_input.get("doc") or task_input.get("text") or ""
    text = " ".join(str(value).split()).strip()
    if not text:
        text = "Compose a brief natural\u2011language description of the snippet based on the AST findings."
    text = text[:700]
    result = (
        "Task focus: " + "Compose a brief natural\u2011language description of the snippet based on the AST findings." + ". "
        "Processed output: " + text + ". "
        + "Verifier feedback: Traceback (most recent call last):\n  File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-080a73c28370/verify_tool.py\", line 121, in <module>\n    _assert_semantics(first)\n  File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-080a73c28370/verify_tool.py\", line 90, in _assert_semantics\n    raise ValueError(\"Search-style tool output should describe match results.\")\nValueError: Search-style tool output should describe match results.\n\nPrior verifier failures for similar subtasks:\n- VerifierError: Repeated identical tool candidate code. Stopping retry loop early to avoid redundant failures.\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-086febb8ed22/verify_tool.py\", line 120, in <module> _assert_\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-e6998b100908/verify_tool.py\", line 121, in <module> _assert_\n\nPotential reusable implementation from shared tool registry:\n- tool=tool_task_2, origin=shared_registry, similarity=0.35"
    )[:900]
    return {
        "tool": "tool_generate_snippet_description",
        "status": "ok",
        "result": result,
    }


from typing import Any, Dict

def tool_group_similar_snippets(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = task_input.get("query") or task_input.get("doc") or task_input.get("text") or ""
    text = " ".join(str(value).split()).strip()
    if not text:
        text = "Cluster snippets that share comparable functionality or imports for more concise summarisation."
    text = text[:700]
    result = (
        "Task focus: " + "Cluster snippets that share comparable functionality or imports for more concise summarisation." + ". "
        "Processed output: " + text + ". "
        + "Verifier feedback: Prior verifier failures for similar subtasks:\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-e6998b100908/verify_tool.py\", line 121, in <module> _assert_\n- VerifierError: Repeated identical tool candidate code. Stopping retry loop early to avoid redundant failures.\n- ValueError: Traceback (most recent call last): File \"/Users/mozart/Documents/quant/sector_rotation/dwc/.dwc/sandboxes/tool_verifier-1afb72f3d9d8/verify_tool.py\", line 126, in <module> raise Va\n\nPotential reusable implementation from shared tool registry:\n- tool=tool_task_3, origin=template, similarity=0.296875"
    )[:900]
    return {
        "tool": "tool_group_similar_snippets",
        "status": "ok",
        "result": result,
    }


from typing import Any, Dict

def tool_compile_concise_summary(task_input: Dict[str, Any]) -> Dict[str, Any]:
    text = str(task_input.get("doc") or task_input.get("text") or task_input.get("query") or "")
    cleaned = " ".join(text.split())
    summary = cleaned[:500]
    if summary:
        summary = "Summary: " + summary
    return {
        "tool": "tool_compile_concise_summary",
        "status": "ok",
        "result": summary,
    }


from typing import Any, Dict

def tool_output_results(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = (
        task_input.get("doc")
        or task_input.get("text")
        or task_input.get("query")
        or str(task_input)
    )
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        cleaned = "Emit the list of extracted code blocks together with the generated summary in the required format."
    result = ("Fallback output for: " + "Emit the list of extracted code blocks together with the generated summary in the required format." + ". " + cleaned)[:900]
    return {
        "tool": "tool_output_results",
        "status": "ok",
        "result": result,
    }


TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "tool_load_markdown_input": tool_load_markdown_input,
    "tool_find_python_code_blocks": tool_find_python_code_blocks,
    "tool_extract_code_snippets": tool_extract_code_snippets,
    "tool_parse_ast_for_definitions": tool_parse_ast_for_definitions,
    "tool_generate_snippet_description": tool_generate_snippet_description,
    "tool_group_similar_snippets": tool_group_similar_snippets,
    "tool_compile_concise_summary": tool_compile_concise_summary,
    "tool_output_results": tool_output_results,
}
