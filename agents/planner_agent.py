"""
Interactive planning agent for plan mode.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from dwc.agents.langchain_tool_calling import invoke_bound_schema
from dwc.agents.spec_generator import LLMProtocol

LOGGER = logging.getLogger(__name__)


class PlanResult(BaseModel):
    requirements_text: str
    proposed_plan: str
    intent_summary: str
    iterations: int = 1


class ProposedPlanPayload(BaseModel):
    steps: list[str] = Field(default_factory=list)


class IntentSummaryPayload(BaseModel):
    intent_summary: str = ""


class PlannerAgent:
    def __init__(self, llm: Optional[LLMProtocol] = None) -> None:
        self.llm = llm

    def propose_plan(
        self, requirements_text: str, refinement_notes: Optional[str] = None
    ) -> str:
        if self.llm is not None:
            try:
                return self._propose_with_llm(requirements_text, refinement_notes)
            except Exception as exc:
                LOGGER.warning("PlannerAgent fallback to heuristic plan: %s", exc)
        return self._heuristic_plan(requirements_text, refinement_notes)

    def capture_intent(self, requirements_text: str, approved_plan: str) -> str:
        if self.llm is not None:
            try:
                bound = invoke_bound_schema(
                    self.llm,
                    prompt=(
                        "Summarize the user intent in under 120 words.\n\n"
                        f"Requirements:\n{requirements_text}\n\n"
                        f"Approved plan:\n{approved_plan}\n"
                    ),
                    schema=IntentSummaryPayload,
                )
                if bound is not None:
                    summary = str(bound.intent_summary).strip()
                    if summary:
                        return summary

                prompt = (
                    "Summarize the user intent in under 120 words.\n\n"
                    f"Requirements:\n{requirements_text}\n\n"
                    f"Approved plan:\n{approved_plan}\n"
                )
                response = self.llm.invoke(prompt)
                text = getattr(response, "content", None)
                if text is None:
                    text = str(response)
                if isinstance(text, list):
                    text = " ".join(str(item) for item in text)
                summary = str(text).strip()
                if summary:
                    return summary
            except Exception as exc:
                LOGGER.warning("PlannerAgent fallback to heuristic intent: %s", exc)
        return self._heuristic_intent(requirements_text, approved_plan)

    def _propose_with_llm(
        self, requirements_text: str, refinement_notes: Optional[str]
    ) -> str:
        prompt = f"""
Create a concise plan for implementing this workflow compiler request.
Return plain text with numbered steps only.

Requirements:
{requirements_text}

Refinement notes:
{refinement_notes or "None"}
"""
        bound = invoke_bound_schema(self.llm, prompt=prompt, schema=ProposedPlanPayload)
        if bound is not None:
            steps = [str(step).strip() for step in bound.steps if str(step).strip()]
            if steps:
                return "\n".join(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))

        response = self.llm.invoke(prompt)
        text = getattr(response, "content", None)
        if text is None:
            text = str(response)
        if isinstance(text, list):
            text = " ".join(str(item) for item in text)
        plan = str(text).strip()
        if not plan:
            raise ValueError("Empty plan from LLM")
        return plan

    @staticmethod
    def _heuristic_plan(
        requirements_text: str, refinement_notes: Optional[str]
    ) -> str:
        lines = [
            "1. Parse requirements and lock the current task description in shared memory.",
            "2. Split the task into independent subtasks for tool construction.",
            "3. Build one tool function per subtask via tool-builder agents.",
            "4. Verify each tool in a venv with execution-based integrity checks.",
            "5. Iterate tool fixes until verifier passes or fallback tool is selected.",
            "6. Assemble a LangGraph workflow that runs subtasks and synthesizes results.",
            "7. Emit workflow folder with workflow.py, tools.py, README.md, and memory snapshot.",
            "8. Validate generated code and return user run instructions.",
        ]
        if refinement_notes:
            lines.append(f"9. Apply refinement focus: {refinement_notes.strip()}")
        return "\n".join(lines)

    @staticmethod
    def _heuristic_intent(requirements_text: str, approved_plan: str) -> str:
        condensed_req = re.sub(r"\s+", " ", requirements_text).strip()
        condensed_plan = re.sub(r"\s+", " ", approved_plan).strip()
        if len(condensed_req) > 300:
            condensed_req = condensed_req[:297] + "..."
        if len(condensed_plan) > 300:
            condensed_plan = condensed_plan[:297] + "..."
        return (
            "Build a general-purpose workflow generator from natural language "
            f"requirements. User context: {condensed_req} "
            f"Execution path: {condensed_plan}"
        )
