"""
Synthesis agent that prepares final-answer prompts.
"""

from __future__ import annotations

import logging
from typing import Optional

from dwc.agents.spec_generator import LLMProtocol

LOGGER = logging.getLogger(__name__)


class SynthesisAgent:
    def __init__(self, llm: Optional[LLMProtocol] = None) -> None:
        self.llm = llm

    def synthesis_prompt(
        self,
        *,
        requirements_text: str,
        approved_plan: Optional[str],
        intent_summary: Optional[str],
    ) -> str:
        if self.llm is not None:
            try:
                prompt = (
                    "Create a concise synthesis prompt for combining subtask outputs "
                    "into one final plain-text user answer.\n\n"
                    f"Requirements:\n{requirements_text}\n\n"
                    f"Approved plan:\n{approved_plan or 'None'}\n\n"
                    f"Intent summary:\n{intent_summary or 'None'}\n"
                )
                response = self.llm.invoke(prompt)
                text = getattr(response, "content", None)
                if text is None:
                    text = str(response)
                if isinstance(text, list):
                    text = " ".join(str(item) for item in text)
                cleaned = str(text).strip()
                if cleaned:
                    return cleaned
            except Exception as exc:
                LOGGER.warning("SynthesisAgent fallback to deterministic prompt: %s", exc)

        return (
            "You are the synthesis head. Combine independent subtask outputs into one "
            "clear, direct plain-text answer for the user. Keep the answer coherent "
            "with the approved plan and user intent. Avoid JSON output."
        )
