"""
Execution-based verifier for generated tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from dwc.agents.tool_builder_agent import ToolCandidate
from dwc.runtime.sandbox import SandboxConfig, VenvSandbox


class ToolVerificationResult(BaseModel):
    success: bool
    errors: Optional[str] = None
    output_preview: Optional[str] = None


class ToolVerifierAgent:
    def __init__(self, sandbox: Optional[VenvSandbox] = None) -> None:
        self.sandbox = sandbox or VenvSandbox(
            SandboxConfig(timeout_seconds=60, preserve_session=False)
        )

    def verify(self, candidate: ToolCandidate) -> ToolVerificationResult:
        session = self.sandbox.create_session("tool_verifier")
        try:
            module_path = session.root_dir / "tool_under_test.py"
            module_path.write_text(
                self._tool_module_with_safe_cli(candidate.code), encoding="utf-8"
            )

            harness_path = session.root_dir / "verify_tool.py"
            harness_code = self._harness_code(candidate)
            harness_path.write_text(harness_code, encoding="utf-8")

            result = self.sandbox.run_script(
                session=session,
                script_path=str(harness_path),
                script_args=[],
                input_payload=None,
                timeout_seconds=45,
            )
            if result.exit_code != 0:
                return ToolVerificationResult(
                    success=False,
                    errors=(result.stderr or result.stdout or "Verifier failed.").strip(),
                )

            payload = self._parse_last_json_line(result.stdout)
            preview = str(payload.get("preview", ""))[:400]
            return ToolVerificationResult(success=True, output_preview=preview)
        except Exception as exc:
            return ToolVerificationResult(success=False, errors=str(exc))
        finally:
            self.sandbox.cleanup(session)

    @staticmethod
    def _harness_code(candidate: ToolCandidate) -> str:
        sample_json = json.dumps(candidate.sample_input, sort_keys=True)
        description_json = json.dumps(candidate.description, sort_keys=True)
        expected_tool_name_json = json.dumps(candidate.name, sort_keys=True)
        return f"""\
import json
from copy import deepcopy
from tool_under_test import {candidate.name} as tool_under_test

payload = {sample_json}
subtask_description = {description_json}
expected_tool_name = {expected_tool_name_json}


def _normalize(value):
    if isinstance(value, dict):
        return {{str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value).strip()


def _contains_any(text, hints):
    lowered = str(text or "").lower()
    return any(hint in lowered for hint in hints)


def _parse_json_if_possible(value):
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _assert_contract(result):
    if not isinstance(result, dict):
        raise TypeError("Tool output must be a dict.")
    for required in ("tool", "status", "result"):
        if required not in result:
            raise ValueError(f"Tool output must contain '{{required}}'.")
    if str(result.get("tool") or "").strip() != expected_tool_name:
        raise ValueError(
            f"Tool output 'tool' field must match function name '{{expected_tool_name}}'."
        )
    status_value = str(result.get("status") or "").strip().lower()
    if status_value not in ("ok", "success"):
        raise ValueError(f"Tool status must indicate success. Got: {{result.get('status')}}")

    result_value = result.get("result")
    if result_value is None:
        raise ValueError("Tool output 'result' cannot be None.")
    if isinstance(result_value, str) and not result_value.strip():
        raise ValueError("Tool output 'result' cannot be empty text.")


def _assert_semantics(result):
    result_value = result.get("result")
    result_text = str(result_value).strip()
    lower_result = result_text.lower()
    payload_text = str(payload).strip()
    source_text = str(payload.get("doc") or payload.get("text") or "").strip()
    query_text = str(payload.get("query") or "").strip()
    lower_subtask = subtask_description.lower()

    if "subtask:" in lower_result and "input:" in lower_result:
        raise ValueError("Tool output appears to be template scaffolding, not task execution.")

    if result_text and result_text == payload_text:
        raise ValueError("Tool output mirrors the entire payload without processing.")

    identity_allowed = _contains_any(
        lower_subtask,
        ("echo", "repeat", "identity", "return input", "pass through", "passthrough"),
    )
    if query_text and result_text == query_text and not identity_allowed:
        raise ValueError("Tool output mirrors query input without transformation.")
    if source_text and result_text == source_text and not identity_allowed:
        raise ValueError("Tool output mirrors source text without transformation.")

    if _contains_any(lower_subtask, ("search", "find", "grep", "ripgrep", "scan files", "locate symbol")):
        parsed = _parse_json_if_possible(result_value)
        if isinstance(parsed, dict):
            if not any(key in parsed for key in ("matches", "total_matches", "results", "output")):
                raise ValueError(
                    "Search-style tool output should include matches/total_matches/results/output."
                )
        elif not _contains_any(lower_result, ("match", "found", "result", "no match")):
            raise ValueError("Search-style tool output should describe match results.")

    if _contains_any(lower_subtask, ("summarize", "summary", "compress")) and len(source_text) >= 120:
        if len(result_text) >= len(source_text):
            raise ValueError("Summary output should be shorter than source text.")

    if _contains_any(lower_subtask, ("shell command", "terminal command", "command line", "cli command", "run shell", "execute shell")):
        parsed = _parse_json_if_possible(result_value)
        if not isinstance(parsed, dict):
            raise ValueError("Shell command tool output should be JSON object text.")
        if "command" not in parsed or "output" not in parsed:
            raise ValueError("Shell command output JSON should include 'command' and 'output'.")


def _is_nondeterministic_task():
    return _contains_any(
        subtask_description,
        (
            "current time",
            "timestamp",
            "date",
            "clock",
            "random",
            "uuid",
            "nonce",
        ),
    )


first = tool_under_test(deepcopy(payload))
_assert_contract(first)
_assert_semantics(first)

if not _is_nondeterministic_task():
    second = tool_under_test(deepcopy(payload))
    if _normalize(first) != _normalize(second):
        raise ValueError("Tool output is non-deterministic for identical input.")

preview = str(first.get("result", ""))[:400]
print(json.dumps({{"preview": preview}}))
"""

    @staticmethod
    def _parse_last_json_line(stdout: str) -> dict:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return {}
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {}

    @staticmethod
    def _tool_module_with_safe_cli(tool_code: str) -> str:
        prelude = """\
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

def _decision_from_user_message(user_message: str, command: str):
    message = user_message.strip()
    lowered = message.lower()
    if lowered.startswith("modify:"):
        replacement = message.split(":", 1)[1].strip()
        if replacement:
            return "execute", replacement
    if lowered.startswith("replace with "):
        replacement = message[len("replace with ") :].strip()
        if replacement:
            return "execute", replacement
    if any(
        token in lowered for token in ("execute", "run", "yes", "approve", "proceed", "continue")
    ):
        return "execute", command
    if any(
        token in lowered
        for token in ("skip", "no", "deny", "block", "cancel", "stop", "other", "something else")
    ):
        return "skip", None
    return "skip", None

def _prompt_shell_decision(command: str):
    print("[safe_cli] Pending shell command:")
    print(f"[safe_cli]   {command}")
    print("[safe_cli] Reply: execute | modify:<new command> | skip")
    user_message = input("[safe_cli] > ").strip()
    return _decision_from_user_message(user_message, command)

def _resolve_shell_command(command: str, user_message=None):
    # In verifier context default to allow so non-interactive checks can run.
    mode = os.getenv("DWC_SAFE_CLI_MODE", "allow").strip().lower()
    if mode == "allow":
        return command
    if mode == "deny":
        return None
    seed_message = str(user_message or "").strip()
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

def safe_cli(command: str, user_message=None) -> str:
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

"""
        return prelude + "\n" + tool_code
