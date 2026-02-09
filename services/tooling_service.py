"""
Tooling-stage service for subtask decomposition and verified tool construction.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dwc.agents.subtask_agent import SubtaskAgent, SubtaskSpec
from dwc.agents.tool_builder_agent import ToolBuilderAgent, ToolCandidate
from dwc.agents.tool_verifier_agent import ToolVerificationResult, ToolVerifierAgent
from dwc.memory.agent_todo_board import AgentTodoBoard
from dwc.memory.history_store import HistoryStore
from dwc.memory.markdown_memory import MarkdownMemoryStore
from dwc.memory.shared_tool_registry import SharedToolRegistry


class ToolBuildRecord(BaseModel):
    subtask_id: str
    subtask_description: str
    tool_name: str
    origin: str = "unknown"
    attempts: int = 1
    verified: bool = False
    verifier_feedback: str = ""
    preview: str = ""


class ToolingStageResult(BaseModel):
    subtasks: List[SubtaskSpec] = Field(default_factory=list)
    subtask_rows: List[Dict[str, str]] = Field(default_factory=list)
    tool_functions: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    tool_records: List[ToolBuildRecord] = Field(default_factory=list)


class ToolingService:
    def __init__(
        self,
        *,
        subtask_agent: SubtaskAgent,
        tool_builder: ToolBuilderAgent,
        tool_verifier: ToolVerifierAgent,
        memory_store: MarkdownMemoryStore,
        history_store: HistoryStore,
        shared_tool_registry: Optional[SharedToolRegistry] = None,
        todo_board: Optional[AgentTodoBoard] = None,
    ) -> None:
        self.subtask_agent = subtask_agent
        self.tool_builder = tool_builder
        self.tool_verifier = tool_verifier
        self.memory_store = memory_store
        self.history_store = history_store
        self.shared_tool_registry = shared_tool_registry or SharedToolRegistry()
        self.todo_board = todo_board

    def build_verified_tools(
        self,
        *,
        workflow_name: str,
        requirements_text: str,
        approved_plan: str,
        current_task_description: str,
        max_subtasks: int = 8,
        max_tool_iterations: int = 4,
    ) -> ToolingStageResult:
        if self.todo_board is not None:
            self.todo_board.start(
                "subtask_agent",
                "split_subtasks",
                "Splitting requirements into executable subtasks.",
            )
        subtasks = self.subtask_agent.split(
            requirements_text,
            approved_plan=approved_plan,
            max_subtasks=max_subtasks,
        )
        if self.todo_board is not None:
            self.todo_board.complete(
                "subtask_agent",
                "split_subtasks",
                f"Created {len(subtasks)} subtask(s).",
            )
            self.todo_board.start(
                "tool_builder_agent",
                "build_tools",
                f"Building candidate tools for {len(subtasks)} subtask(s).",
            )
            self.todo_board.start(
                "tool_verifier_agent",
                "verify_tools",
                "Verifying tool contract and semantics.",
            )
        self.memory_store.append_agent_working_memory(
            "subtask_agent",
            "Created subtasks:\n"
            + "\n".join(
                f"- {subtask.id}: {subtask.description}" for subtask in subtasks
            ),
        )

        tool_records: List[ToolBuildRecord] = []
        tool_functions: Dict[str, Dict[str, str]] = {}
        subtask_rows: List[Dict[str, str]] = []

        for subtask in subtasks:
            if self.todo_board is not None:
                self.todo_board.add_check(
                    "tool_builder_agent",
                    "build_tools",
                    f"Subtask `{subtask.id}`: {subtask.description[:120]}",
                )
            shared_suggestion = self._suggest_shared_tool(subtask.description)
            guidance = self._build_prior_failure_guidance(subtask.description)
            shared_guidance = self._build_shared_tool_guidance(shared_suggestion)
            seed_feedback = self._merge_feedback(guidance, shared_guidance)
            feedback = seed_feedback
            if seed_feedback:
                self.memory_store.append_agent_working_memory(
                    "tool_builder_agent",
                    (
                        f"Subtask `{subtask.id}` seeded with guidance:\n"
                        f"{seed_feedback}"
                    ),
                )
            chosen_candidate = None
            chosen_verification = ToolVerificationResult(success=False, errors="Not run")
            attempts = 0
            seen_code_hashes: set[str] = set()

            registry_candidate = self._candidate_from_shared_suggestion(
                subtask=subtask,
                shared_suggestion=shared_suggestion,
            )
            if registry_candidate is not None:
                attempts += 1
                candidate_hash = hashlib.sha256(
                    registry_candidate.code.encode("utf-8")
                ).hexdigest()
                seen_code_hashes.add(candidate_hash)
                if self.todo_board is not None:
                    self.todo_board.add_check(
                        "tool_builder_agent",
                        "build_tools",
                        f"{subtask.id} attempt {attempts}: reused shared registry candidate.",
                    )
                verification = self.tool_verifier.verify(registry_candidate)
                self._record_attempt(
                    workflow_name=workflow_name,
                    subtask=subtask,
                    candidate_name=registry_candidate.name,
                    candidate_origin=registry_candidate.origin,
                    candidate_code=registry_candidate.code,
                    candidate_sample_input=registry_candidate.sample_input,
                    attempt=attempts,
                    verification=verification,
                    feedback_used="shared_registry_candidate",
                    contributor="subtask_agent+tool_verifier_agent:shared_registry",
                )
                if self.todo_board is not None:
                    self.todo_board.add_check(
                        "tool_verifier_agent",
                        "verify_tools",
                        (
                            f"{registry_candidate.name} (shared_registry) "
                            f"success={verification.success}"
                        ),
                    )
                self.memory_store.append_agent_working_memory(
                    "tool_verifier_agent",
                    (
                        f"Shared registry candidate `{registry_candidate.name}` for subtask "
                        f"`{subtask.id}` verification success={verification.success}.\n"
                        f"Verifier feedback: {verification.errors or verification.output_preview or 'OK'}"
                    ),
                )
                chosen_candidate = registry_candidate
                chosen_verification = verification
                if not verification.success:
                    feedback = self._compose_retry_feedback(
                        error_text=verification.errors or "Verifier rejected output.",
                        guidance=seed_feedback,
                    )

            for _ in range(max_tool_iterations):
                if chosen_verification.success:
                    break
                attempts += 1
                candidate = self.tool_builder.build_tool(
                    subtask=subtask,
                    shared_task_description=current_task_description,
                    feedback=feedback,
                )
                candidate_hash = hashlib.sha256(candidate.code.encode("utf-8")).hexdigest()
                if self.todo_board is not None:
                    self.todo_board.add_check(
                        "tool_builder_agent",
                        "build_tools",
                        (
                            f"{subtask.id} attempt {attempts}: "
                            f"candidate `{candidate.name}` origin={candidate.origin}."
                        ),
                    )
                if candidate_hash in seen_code_hashes:
                    repeat_error = (
                        "Repeated identical tool candidate code. "
                        "Stopping retry loop early to avoid redundant failures."
                    )
                    verification = ToolVerificationResult(success=False, errors=repeat_error)
                    self._record_attempt(
                        workflow_name=workflow_name,
                        subtask=subtask,
                        candidate_name=candidate.name,
                        candidate_origin=candidate.origin,
                        candidate_code=candidate.code,
                        candidate_sample_input=candidate.sample_input,
                        attempt=attempts,
                        verification=verification,
                        feedback_used=feedback,
                        contributor=(
                            "subtask_agent+tool_builder_agent+tool_verifier_agent:"
                            f"{candidate.origin}"
                        ),
                    )
                    if self.todo_board is not None:
                        self.todo_board.add_check(
                            "tool_verifier_agent",
                            "verify_tools",
                            f"{candidate.name} skipped verifier: repeated code hash.",
                        )
                    chosen_candidate = candidate
                    chosen_verification = verification
                    break
                seen_code_hashes.add(candidate_hash)
                self.memory_store.append_agent_working_memory(
                    "tool_builder_agent",
                    (
                        f"Subtask `{subtask.id}` attempt {attempts} created tool `{candidate.name}` "
                        f"(origin={candidate.origin}).\n"
                        f"Feedback used: {feedback or 'None'}"
                    ),
                )

                verification = self.tool_verifier.verify(candidate)
                if self.todo_board is not None:
                    self.todo_board.add_check(
                        "tool_verifier_agent",
                        "verify_tools",
                        f"{candidate.name} verification success={verification.success}.",
                    )
                self._record_attempt(
                    workflow_name=workflow_name,
                    subtask=subtask,
                    candidate_name=candidate.name,
                    candidate_origin=candidate.origin,
                    candidate_code=candidate.code,
                    candidate_sample_input=candidate.sample_input,
                    attempt=attempts,
                    verification=verification,
                    feedback_used=feedback,
                    contributor=(
                        "subtask_agent+tool_builder_agent+tool_verifier_agent:"
                        f"{candidate.origin}"
                    ),
                )
                self.memory_store.append_agent_working_memory(
                    "tool_verifier_agent",
                    (
                        f"Tool `{candidate.name}` for subtask `{subtask.id}` "
                        f"verification success={verification.success}.\n"
                        f"Verifier feedback: {verification.errors or verification.output_preview or 'OK'}"
                    ),
                )
                if verification.success:
                    chosen_candidate = candidate
                    chosen_verification = verification
                    break

                feedback = self._compose_retry_feedback(
                    error_text=verification.errors or "Verifier rejected output.",
                    guidance=seed_feedback,
                )
                chosen_candidate = candidate
                chosen_verification = verification

            if chosen_candidate is None:
                chosen_candidate = self.tool_builder.build_fallback_tool(subtask=subtask)
                chosen_verification = self.tool_verifier.verify(chosen_candidate)
                attempts += 1
                if self.todo_board is not None:
                    self.todo_board.add_check(
                        "tool_builder_agent",
                        "build_tools",
                        f"{subtask.id}: using fallback tool `{chosen_candidate.name}`.",
                    )
                    self.todo_board.add_check(
                        "tool_verifier_agent",
                        "verify_tools",
                        (
                            f"{chosen_candidate.name} (fallback) "
                            f"success={chosen_verification.success}"
                        ),
                    )
                self._record_attempt(
                    workflow_name=workflow_name,
                    subtask=subtask,
                    candidate_name=chosen_candidate.name,
                    candidate_origin=chosen_candidate.origin,
                    candidate_code=chosen_candidate.code,
                    candidate_sample_input=chosen_candidate.sample_input,
                    attempt=attempts,
                    verification=chosen_verification,
                    feedback_used="fallback_after_no_candidate",
                    contributor="subtask_agent+tool_builder_agent+tool_verifier_agent:fallback",
                )

            if not chosen_verification.success:
                fallback = self.tool_builder.build_fallback_tool(subtask=subtask)
                fallback_verification = self.tool_verifier.verify(fallback)
                attempts += 1
                if self.todo_board is not None:
                    self.todo_board.add_check(
                        "tool_builder_agent",
                        "build_tools",
                        f"{subtask.id}: retrying fallback tool `{fallback.name}`.",
                    )
                    self.todo_board.add_check(
                        "tool_verifier_agent",
                        "verify_tools",
                        (
                            f"{fallback.name} (fallback retry) "
                            f"success={fallback_verification.success}"
                        ),
                    )
                self._record_attempt(
                    workflow_name=workflow_name,
                    subtask=subtask,
                    candidate_name=fallback.name,
                    candidate_origin=fallback.origin,
                    candidate_code=fallback.code,
                    candidate_sample_input=fallback.sample_input,
                    attempt=attempts,
                    verification=fallback_verification,
                    feedback_used="fallback_after_failure",
                    contributor="subtask_agent+tool_builder_agent+tool_verifier_agent:fallback",
                )
                if fallback_verification.success:
                    chosen_candidate = fallback
                    chosen_verification = fallback_verification
            if self.todo_board is not None:
                if chosen_verification.success:
                    self.todo_board.add_check(
                        "tool_builder_agent",
                        "build_tools",
                        f"{subtask.id}: selected `{chosen_candidate.name}` in {attempts} attempt(s).",
                    )
                else:
                    self.todo_board.add_check(
                        "tool_builder_agent",
                        "build_tools",
                        f"{subtask.id}: unresolved after {attempts} attempt(s), using last candidate.",
                    )

            tool_functions[chosen_candidate.name] = {
                "description": chosen_candidate.description,
                "code": chosen_candidate.code,
            }
            subtask_rows.append(
                {
                    "id": subtask.id,
                    "name": subtask.name,
                    "description": subtask.description,
                    "tool_name": chosen_candidate.name,
                }
            )
            tool_records.append(
                ToolBuildRecord(
                    subtask_id=subtask.id,
                    subtask_description=subtask.description,
                    tool_name=chosen_candidate.name,
                    origin=chosen_candidate.origin,
                    attempts=attempts,
                    verified=chosen_verification.success,
                    verifier_feedback=chosen_verification.errors or "",
                    preview=chosen_verification.output_preview or "",
                )
            )

        if self.todo_board is not None:
            verified_count = sum(1 for row in tool_records if row.verified)
            status_message = (
                f"Selected {len(tool_records)} tool(s); {verified_count} passed verifier."
            )
            if verified_count == len(tool_records):
                self.todo_board.complete(
                    "tool_builder_agent",
                    "build_tools",
                    status_message,
                )
                self.todo_board.complete(
                    "tool_verifier_agent",
                    "verify_tools",
                    f"All verifier checks passed ({verified_count}/{len(tool_records)}).",
                )
            else:
                self.todo_board.fail(
                    "tool_builder_agent",
                    "build_tools",
                    status_message,
                )
                self.todo_board.fail(
                    "tool_verifier_agent",
                    "verify_tools",
                    f"Verifier shortfall: {verified_count}/{len(tool_records)} passed.",
                )

        return ToolingStageResult(
            subtasks=subtasks,
            subtask_rows=subtask_rows,
            tool_functions=tool_functions,
            tool_records=tool_records,
        )

    def _build_prior_failure_guidance(self, subtask_description: str) -> str:
        rows = self.history_store.similar_failed_attempts(
            subtask_description=subtask_description,
            limit=3,
            candidate_pool=200,
        )
        if not rows:
            return ""

        lines = ["Prior verifier failures for similar subtasks:"]
        for row in rows:
            error_class = row.get("error_class") or "VerifierError"
            snippet = str(row.get("stderr_snippet") or row.get("stdout_snippet") or "").strip()
            snippet = re.sub(r"\s+", " ", snippet)[:180]
            if snippet:
                lines.append(f"- {error_class}: {snippet}")
            else:
                lines.append(f"- {error_class}")
        return "\n".join(lines)

    @staticmethod
    def _compose_retry_feedback(*, error_text: str, guidance: str) -> str:
        if not guidance:
            return error_text
        if guidance in error_text:
            return error_text
        return f"{error_text}\n\n{guidance}"

    @staticmethod
    def _merge_feedback(*parts: str) -> str:
        chunks = [str(part).strip() for part in parts if str(part).strip()]
        if not chunks:
            return ""
        return "\n\n".join(chunks)

    def _suggest_shared_tool(self, subtask_description: str) -> Optional[Dict[str, Any]]:
        try:
            return self.shared_tool_registry.suggest_tool(subtask_description=subtask_description)
        except Exception:
            return None

    @staticmethod
    def _build_shared_tool_guidance(shared_suggestion: Optional[Dict[str, Any]]) -> str:
        if not shared_suggestion:
            return ""
        tool_name = str(shared_suggestion.get("tool_name", "shared_tool")).strip()
        origin = str(shared_suggestion.get("origin", "unknown")).strip()
        similarity = shared_suggestion.get("similarity", 0.0)
        lines = [
            "Potential reusable implementation from shared tool registry:",
            f"- tool={tool_name}, origin={origin}, similarity={similarity}",
        ]
        last_error = str(shared_suggestion.get("last_error", "")).strip()
        if last_error:
            lines.append(f"- latest failure note: {last_error[:180]}")
        return "\n".join(lines)

    def _candidate_from_shared_suggestion(
        self,
        *,
        subtask: SubtaskSpec,
        shared_suggestion: Optional[Dict[str, Any]],
    ) -> Optional[ToolCandidate]:
        if not shared_suggestion:
            return None
        similarity = float(shared_suggestion.get("similarity") or 0.0)
        suggestion_origin = str(shared_suggestion.get("origin") or "").strip().lower()
        if similarity < 0.55:
            return None
        if suggestion_origin == "shared_registry":
            return None

        source_name = str(shared_suggestion.get("tool_name") or "").strip()
        target_name = self._function_name(subtask.id)
        raw_code = str(shared_suggestion.get("code") or "")
        rewritten = self._retarget_tool_code(
            code=raw_code,
            source_name=source_name or target_name,
            target_name=target_name,
        )
        if not rewritten:
            return None
        sample_input = shared_suggestion.get("sample_input")
        if not isinstance(sample_input, dict):
            sample_input = {"query": "Example user request"}

        return ToolCandidate(
            name=target_name,
            description=subtask.description,
            code=rewritten,
            sample_input=sample_input,
            origin="shared_registry",
        )

    @staticmethod
    def _retarget_tool_code(*, code: str, source_name: str, target_name: str) -> str:
        rewritten = str(code or "").strip()
        if not rewritten:
            return ""
        if source_name != target_name:
            pattern = rf"def\s+{re.escape(source_name)}\s*\("
            rewritten, count = re.subn(pattern, f"def {target_name}(", rewritten, count=1)
            if count == 0:
                generic = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", rewritten)
                if generic:
                    current_name = generic.group(1)
                    rewritten = re.sub(
                        rf"def\s+{re.escape(current_name)}\s*\(",
                        f"def {target_name}(",
                        rewritten,
                        count=1,
                    )
                else:
                    return ""
            rewritten = rewritten.replace(
                f'"tool": "{source_name}"',
                f'"tool": "{target_name}"',
            )
            rewritten = rewritten.replace(
                f"'tool': '{source_name}'",
                f"'tool': '{target_name}'",
            )
        try:
            compile(rewritten, "<shared_tool_candidate>", "exec")
        except Exception:
            return ""
        return rewritten + ("\n" if not rewritten.endswith("\n") else "")

    @staticmethod
    def _function_name(subtask_id: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", subtask_id).strip("_").lower()
        if not sanitized:
            sanitized = "task"
        if sanitized[0].isdigit():
            sanitized = f"task_{sanitized}"
        sanitized = sanitized[:48].rstrip("_") or "task"
        return f"tool_{sanitized}"

    def _record_attempt(
        self,
        *,
        workflow_name: str,
        subtask: SubtaskSpec,
        candidate_name: str,
        candidate_origin: str,
        candidate_code: str,
        candidate_sample_input: Dict[str, Any],
        attempt: int,
        verification: ToolVerificationResult,
        feedback_used: str,
        contributor: str,
    ) -> None:
        stderr_snippet = (verification.errors or "").strip()[:500]
        stdout_snippet = (verification.output_preview or "").strip()[:500]
        error_class = self._classify_error(stderr_snippet)
        code_hash = hashlib.sha256(candidate_code.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        self.history_store.add_tool_attempt(
            workflow_name=workflow_name,
            subtask_id=subtask.id,
            subtask_description=subtask.description,
            tool_name=candidate_name,
            tool_origin=candidate_origin,
            attempt_index=int(attempt),
            success=verification.success,
            error_class=error_class if not verification.success else None,
            stderr_snippet=stderr_snippet or None,
            stdout_snippet=stdout_snippet or None,
            feedback_used=(feedback_used or "")[:500],
            code_hash=code_hash,
            created_at=created_at,
        )
        self.shared_tool_registry.record_contribution(
            subtask_description=subtask.description,
            tool_name=candidate_name,
            tool_code=candidate_code,
            sample_input=candidate_sample_input,
            origin=candidate_origin,
            contributor=contributor,
            success=verification.success,
            error_text=stderr_snippet or None,
            created_at=created_at,
        )

    @staticmethod
    def _classify_error(error_text: str) -> str:
        lower = (error_text or "").lower()
        if not lower:
            return "None"
        if "syntaxerror" in lower:
            return "SyntaxError"
        if "modulenotfounderror" in lower or "no module named" in lower:
            return "ImportError"
        if "timeout" in lower:
            return "TimeoutError"
        if "typeerror" in lower:
            return "TypeError"
        if "valueerror" in lower:
            return "ValueError"
        if "permission" in lower:
            return "PermissionError"
        if "no such file or directory" in lower:
            return "FileNotFoundError"
        return "VerifierError"
