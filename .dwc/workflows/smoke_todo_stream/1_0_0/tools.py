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

from datetime import datetime, timezone
from typing import Any, Dict

def tool_return_current_time_iso_format(task_input: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).astimezone().isoformat()
    return {
        "tool": "tool_return_current_time_iso_format",
        "status": "ok",
        "result": now,
    }


TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "tool_return_current_time_iso_format": tool_return_current_time_iso_format,
}
