"""
Natural-language to WorkflowSpec generation agent.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Protocol

from pydantic import BaseModel

from dwc.ir.spec_schema import (
    EdgeSpec,
    InputSpec,
    OutputSpec,
    StepSpec,
    WorkflowSpec,
    model_validate_json_compat,
)
from dwc.ir.validators import validate_workflow_spec


class LLMProtocol(Protocol):
    def invoke(self, prompt: Any, **kwargs: Any) -> Any:  # pragma: no cover - protocol only
        ...


class SpecGeneratorConfig(BaseModel):
    temperature: float = 0.0
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"


def _extract_json_block(raw: str) -> Optional[str]:
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0) if match else None


class SpecGeneratorAgent:
    def __init__(
        self,
        llm: Optional[LLMProtocol] = None,
        config: Optional[SpecGeneratorConfig] = None,
    ) -> None:
        self.llm = llm
        self.config = config or SpecGeneratorConfig()

    def generate(self, requirements_text: str, workflow_name: Optional[str] = None) -> WorkflowSpec:
        if self.llm is not None:
            try:
                generated = self._generate_with_llm(requirements_text, workflow_name)
                validate_workflow_spec(generated)
                return generated
            except Exception:
                # Fall back to deterministic template spec.
                pass
        spec = self._heuristic_spec(requirements_text, workflow_name)
        validate_workflow_spec(spec)
        return spec

    def _generate_with_llm(
        self, requirements_text: str, workflow_name: Optional[str]
    ) -> WorkflowSpec:
        name = workflow_name or "compiled_workflow"
        prompt = f"""
You are a workflow compiler. Convert requirements into WorkflowSpec JSON only.
Return valid JSON with no markdown and no explanations.

Schema summary:
- version: semantic version string
- name: workflow name
- description: workflow description
- inputs: list of {{id, name, data_type, required, description, default}}
- outputs: list of {{id, name, data_type, source_step, description}}
- steps: list of {{id, type(llm|tool|condition|transform), config, retry_policy, timeout_seconds}}
- edges: list of {{source, target, condition}}
- constraints: optional list of {{id, kind, expression, severity}}
- metadata: object

Hard constraints:
- Deterministic topology
- Every edge source/target references step ids
- Tool steps must include config.tool_name or config.loader
- LLM steps must include config.model and config.temperature
- Use timeout_seconds >= 30
- Use retry_policy with max_retries and backoff_strategy

Requested name: {name}
Requirements:
{requirements_text}
"""
        response = self.llm.invoke(prompt)
        text = getattr(response, "content", None)
        if text is None:
            text = str(response)
        if isinstance(text, list):
            text = " ".join(str(item) for item in text)
        block = _extract_json_block(str(text))
        if not block:
            raise ValueError("No JSON object found in LLM response.")
        spec = model_validate_json_compat(block)
        if workflow_name:
            spec.name = workflow_name
        return spec

    def _heuristic_spec(
        self, requirements_text: str, workflow_name: Optional[str]
    ) -> WorkflowSpec:
        name = workflow_name or self._infer_name(requirements_text)
        description = requirements_text.strip().splitlines()[0][:200] or "Compiled workflow"

        step_ingest = StepSpec(
            id="ingest_input",
            type="tool",
            config={"tool_name": "passthrough"},
            timeout_seconds=60,
        )
        step_llm = StepSpec(
            id="process_with_llm",
            type="llm",
            config={
                "model": self.config.model_id,
                "temperature": self.config.temperature,
                "prompt": (
                    "You are compiling a workflow behavior. "
                    "Requirements: " + requirements_text + "\n"
                    "Input payload: {input}"
                ),
                "output_format": "json",
                "max_output_tokens": 1024,
            },
            timeout_seconds=120,
        )

        spec = WorkflowSpec(
            version="1.0.0",
            name=name,
            description=description,
            inputs=[
                InputSpec(
                    id="input_payload",
                    name="input_payload",
                    data_type="object",
                    required=True,
                    description="Input payload for workflow execution.",
                )
            ],
            outputs=[
                OutputSpec(
                    id="result",
                    name="result",
                    data_type="object",
                    source_step="process_with_llm",
                    description="Final workflow result.",
                )
            ],
            steps=[step_ingest, step_llm],
            edges=[EdgeSpec(source="ingest_input", target="process_with_llm")],
            metadata={"generator": "heuristic_fallback"},
        )
        return spec

    @staticmethod
    def _infer_name(requirements_text: str) -> str:
        first_line = requirements_text.strip().splitlines()[0] if requirements_text.strip() else "workflow"
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", first_line.lower()).strip("_")
        return slug[:48] or "compiled_workflow"


def build_chat_bedrock_converse(model_id: str, region_name: Optional[str] = None) -> LLMProtocol:
    """
    Factory for ChatBedrockConverse client.
    """

    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=model_id, temperature=0, region_name=region_name)
