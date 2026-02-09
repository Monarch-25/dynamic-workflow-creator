"""
Subtask decomposition agent.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from dwc.agents.langchain_tool_calling import invoke_bound_schema
from dwc.agents.spec_generator import LLMProtocol

LOGGER = logging.getLogger(__name__)


class SubtaskSpec(BaseModel):
    id: str
    description: str


class SubtaskSplitRow(BaseModel):
    id: str
    description: str


class SubtaskSplitPayload(BaseModel):
    subtasks: List[SubtaskSplitRow] = Field(default_factory=list)


class SubtaskAgent:
    def __init__(self, llm: Optional[LLMProtocol] = None) -> None:
        self.llm = llm

    def split(
        self,
        requirements_text: str,
        *,
        approved_plan: Optional[str] = None,
        max_subtasks: int = 8,
    ) -> List[SubtaskSpec]:
        if self.llm is not None:
            try:
                tasks = self._split_with_llm(
                    requirements_text, approved_plan=approved_plan, max_subtasks=max_subtasks
                )
                if tasks:
                    return tasks
            except Exception as exc:
                LOGGER.warning("SubtaskAgent fallback to heuristic split: %s", exc)
        return self._heuristic_split(requirements_text, max_subtasks=max_subtasks)

    def _split_with_llm(
        self,
        requirements_text: str,
        *,
        approved_plan: Optional[str],
        max_subtasks: int,
    ) -> List[SubtaskSpec]:
        prompt = f"""
Split this requirement into independent executable subtasks.
Return JSON list only: [{{"id":"task_1","description":"..."}}]
Keep at most {max_subtasks} items.

Requirements:
{requirements_text}

Approved plan:
{approved_plan or "None"}
"""
        bound = invoke_bound_schema(self.llm, prompt=prompt, schema=SubtaskSplitPayload)
        if bound is not None and bound.subtasks:
            subtasks: List[SubtaskSpec] = []
            for idx, row in enumerate(bound.subtasks[:max_subtasks], start=1):
                desc = str(row.description).strip()
                if not desc:
                    continue
                task_id = str(row.id or f"task_{idx}").strip() or f"task_{idx}"
                subtasks.append(SubtaskSpec(id=task_id, description=desc))
            if subtasks:
                return subtasks

        response = self.llm.invoke(prompt)
        text = getattr(response, "content", None)
        if text is None:
            text = str(response)
        if isinstance(text, list):
            text = " ".join(str(item) for item in text)
        body = self._extract_json_block(str(text))
        rows = json.loads(body)
        subtasks: List[SubtaskSpec] = []
        for idx, row in enumerate(rows[:max_subtasks], start=1):
            desc = str(row.get("description", "")).strip()
            if not desc:
                continue
            task_id = str(row.get("id", f"task_{idx}")).strip() or f"task_{idx}"
            subtasks.append(SubtaskSpec(id=task_id, description=desc))
        return subtasks

    @staticmethod
    def _heuristic_split(requirements_text: str, max_subtasks: int) -> List[SubtaskSpec]:
        text = requirements_text.strip()
        if not text:
            return [SubtaskSpec(id="task_1", description="Handle user request.")]

        normalized = text
        normalized = re.sub(r"\s*->\s*", "\n", normalized)
        normalized = re.sub(r"\b(and then|then|after that|next)\b", "\n", normalized, flags=re.I)
        normalized = re.sub(r"\n{2,}", "\n", normalized)

        rough_parts = re.split(r"[\n;]+", normalized)
        parts: List[str] = []
        for part in rough_parts:
            sentence_parts = re.split(r"\.\s+", part.strip())
            for sentence in sentence_parts:
                candidate = sentence.strip(" -\t\r\n.")
                if len(candidate) < 3:
                    continue
                parts.append(candidate)

        if not parts:
            parts = [text]

        # Deduplicate while preserving order.
        seen = set()
        unique_parts: List[str] = []
        for part in parts:
            key = re.sub(r"\s+", " ", part.lower())
            if key not in seen:
                unique_parts.append(part)
                seen.add(key)

        subtasks: List[SubtaskSpec] = []
        for idx, part in enumerate(unique_parts[:max_subtasks], start=1):
            subtasks.append(SubtaskSpec(id=f"task_{idx}", description=part))
        return subtasks or [SubtaskSpec(id="task_1", description=text)]

    @staticmethod
    def _extract_json_block(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return stripped
        match = re.search(r"\[.*\]", stripped, re.DOTALL)
        if not match:
            raise ValueError("No JSON list found in LLM response.")
        return match.group(0)
