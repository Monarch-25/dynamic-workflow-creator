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
    name: str = ""
    description: str


class SubtaskSplitRow(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""


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
Return JSON list only with this shape:
[{{"id":"semantic_snake_case","name":"Short Human Name","description":"..."}}]
Rules:
- Keep at most {max_subtasks} items.
- IDs must be semantic snake_case names, not generic task_1/task_2 unless unavoidable.
- Names should be concise (2-5 words).

Requirements:
{requirements_text}

Approved plan:
{approved_plan or "None"}
"""
        bound = invoke_bound_schema(self.llm, prompt=prompt, schema=SubtaskSplitPayload)
        if bound is not None and bound.subtasks:
            subtasks = self._normalize_rows(bound.subtasks, max_subtasks=max_subtasks)
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
        return self._normalize_rows(rows, max_subtasks=max_subtasks)

    @classmethod
    def _heuristic_split(cls, requirements_text: str, max_subtasks: int) -> List[SubtaskSpec]:
        text = requirements_text.strip()
        if not text:
            return [
                SubtaskSpec(
                    id="handle_user_request",
                    name="Handle Request",
                    description="Handle user request.",
                )
            ]

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

        rows = [{"id": "", "name": "", "description": part} for part in unique_parts[:max_subtasks]]
        subtasks = cls._normalize_rows(rows, max_subtasks=max_subtasks)
        return subtasks or [
            SubtaskSpec(
                id="handle_user_request",
                name="Handle Request",
                description=text,
            )
        ]

    @classmethod
    def _normalize_rows(cls, rows: List[Any], *, max_subtasks: int) -> List[SubtaskSpec]:
        subtasks: List[SubtaskSpec] = []
        used_ids = set()
        for idx, row in enumerate(rows[:max_subtasks], start=1):
            if isinstance(row, BaseModel):
                row_payload = row.model_dump() if hasattr(row, "model_dump") else row.dict()
            elif isinstance(row, dict):
                row_payload = row
            else:
                row_payload = {"description": str(row)}

            desc = str(row_payload.get("description", "")).strip()
            if not desc:
                continue
            semantic_id = cls._build_semantic_subtask_id(
                raw_id=str(row_payload.get("id", "")),
                description=desc,
                index=idx,
                used_ids=used_ids,
            )
            used_ids.add(semantic_id)
            display_name = cls._derive_subtask_name(
                raw_name=str(row_payload.get("name", "")),
                description=desc,
            )
            subtasks.append(
                SubtaskSpec(
                    id=semantic_id,
                    name=display_name,
                    description=desc,
                )
            )
        return subtasks

    @staticmethod
    def _build_semantic_subtask_id(
        *,
        raw_id: str,
        description: str,
        index: int,
        used_ids: set[str],
    ) -> str:
        candidate = re.sub(r"[^a-zA-Z0-9_]+", "_", raw_id.strip().lower()).strip("_")
        if not candidate or re.fullmatch(r"(task|step|subtask)_?\d*", candidate):
            candidate = SubtaskAgent._slug_from_description(description)
        if not candidate:
            candidate = f"task_{index}"
        if candidate[0].isdigit():
            candidate = f"task_{candidate}"
        candidate = candidate[:48].strip("_") or f"task_{index}"
        unique = candidate
        suffix = 2
        while unique in used_ids:
            unique = f"{candidate}_{suffix}"
            suffix += 1
        return unique

    @staticmethod
    def _slug_from_description(text: str) -> str:
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "to",
            "for",
            "of",
            "with",
            "in",
            "on",
            "from",
            "using",
        }
        filtered = [token for token in tokens if token not in stop_words]
        return "_".join(filtered[:6]).strip("_")

    @staticmethod
    def _derive_subtask_name(*, raw_name: str, description: str) -> str:
        candidate = str(raw_name or "").strip()
        if candidate:
            return re.sub(r"\s+", " ", candidate)[:80]
        words = re.findall(r"[a-zA-Z0-9]+", description)
        if not words:
            return "Subtask"
        return " ".join(words[:5])[:80]

    @staticmethod
    def _extract_json_block(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return stripped
        match = re.search(r"\[.*\]", stripped, re.DOTALL)
        if not match:
            raise ValueError("No JSON list found in LLM response.")
        return match.group(0)
