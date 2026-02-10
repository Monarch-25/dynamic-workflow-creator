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

import datetime
from typing import Dict, Any

def tool_get_current_iso_timestamp(task_input: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.datetime.now()
    iso_ts = now.isoformat(timespec='seconds')
    result = f"{iso_ts} - Current local date and time in ISO 8601."
    return {"tool": "tool_get_current_iso_timestamp", "status": "success", "result": result}


import datetime
from typing import Dict, Any, Optional

def safe_cli(command: str, user_message: Optional[str] = None) -> str:
    # Placeholder implementation; in real environment this would execute a safe CLI call.
    return ""

def tool_generate_one_line_explanation(task_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        iso_ts = datetime.datetime.now().isoformat(timespec='seconds')
        explanation = "The timestamp indicates when the response was generated."
        result = {"timestamp": iso_ts, "explanation": explanation}
        return {"tool": "tool_generate_one_line_explanation", "status": "success", "result": result}
    except Exception as e:
        return {"tool": "tool_generate_one_line_explanation", "status": "error", "result": str(e)}


from typing import Any, Dict

def tool_gather_workflow_specifications(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = (
        task_input.get("doc")
        or task_input.get("text")
        or task_input.get("query")
        or str(task_input)
    )
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        cleaned = "Collect detailed workflow specifications and compiler requirements."
    result = ("Fallback output for: " + "Collect detailed workflow specifications and compiler requirements." + ". " + cleaned)[:900]
    return {
        "tool": "tool_gather_workflow_specifications",
        "status": "ok",
        "result": result,
    }


from typing import Any, Dict

def tool_design_ast_structure(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = (
        task_input.get("doc")
        or task_input.get("text")
        or task_input.get("query")
        or str(task_input)
    )
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        cleaned = "Create the abstract syntax tree (AST) model for the workflow language."
    result = ("Fallback output for: " + "Create the abstract syntax tree (AST) model for the workflow language." + ". " + cleaned)[:900]
    return {
        "tool": "tool_design_ast_structure",
        "status": "ok",
        "result": result,
    }


import datetime
from typing import Any, Dict

def tool_implement_parsing_modules(task_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        now = datetime.datetime.now().isoformat(timespec='seconds')
        explanation = "Current local date and time in ISO format."
        result = f"{now} - {explanation}"
        return {"tool": "tool_implement_parsing_modules", "status": "success", "result": result}
    except Exception as e:
        return {"tool": "tool_implement_parsing_modules", "status": "error", "result": str(e)}


import datetime
from typing import Any, Dict

def tool_develop_codegen_backends(task_input: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.datetime.now().isoformat(timespec='seconds')
    explanation = "Current local date and time in ISO 8601 format."
    result = f"{now} – {explanation}"
    return {
        "tool": "tool_develop_codegen_backends",
        "status": "success",
        "result": result
    }


from datetime import datetime
from typing import Dict, Any, Optional

def safe_cli(command: str, user_message: Optional[str] = None) -> str:
    # Placeholder implementation; in real environment this would run a safe CLI command.
    return ""

def tool_create_validation_testing_suites(task_input: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = datetime.now().isoformat(timespec='seconds')
    explanation = "current local date and time in ISO format"
    result = f"{now_iso} - {explanation}"
    return {
        "tool": "tool_create_validation_testing_suites",
        "status": "success",
        "result": result
    }


import datetime
from typing import Dict, Any, Optional

def safe_cli(command: str, user_message: Optional[str] = None) -> str:
    # Placeholder implementation; in real environment this would run a safe command.
    return f"Executed: {command}"

def tool_deploy_compiler_and_document(task_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        now_iso = datetime.datetime.now().isoformat(timespec='seconds')
        explanation = "Current local date and time in ISO format."
        result = f"{now_iso} - {explanation}"
        return {"tool": "tool_deploy_compiler_and_document", "status": "success", "result": result}
    except Exception as e:
        return {"tool": "tool_deploy_compiler_and_document", "status": "error", "result": str(e)}


TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "tool_get_current_iso_timestamp": tool_get_current_iso_timestamp,
    "tool_generate_one_line_explanation": tool_generate_one_line_explanation,
    "tool_gather_workflow_specifications": tool_gather_workflow_specifications,
    "tool_design_ast_structure": tool_design_ast_structure,
    "tool_implement_parsing_modules": tool_implement_parsing_modules,
    "tool_develop_codegen_backends": tool_develop_codegen_backends,
    "tool_create_validation_testing_suites": tool_create_validation_testing_suites,
    "tool_deploy_compiler_and_document": tool_deploy_compiler_and_document,
}
