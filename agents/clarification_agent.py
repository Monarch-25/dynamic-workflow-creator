"""
Spec clarification and validation agent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from dwc.compiler.dependency_resolver import DependencyResolver
from dwc.ir.spec_schema import WorkflowSpec, model_dump_compat
from dwc.ir.validators import validate_workflow_spec
from dwc.llm import DWC_BEDROCK_MODEL_ID


class ClarificationResult(BaseModel):
    spec: WorkflowSpec
    questions: List[str] = Field(default_factory=list)
    modified: bool = False


class ClarificationAgent:
    def __init__(self) -> None:
        self.resolver = DependencyResolver()

    def clarify(
        self,
        spec: WorkflowSpec,
        requirements_text: Optional[str] = None,
    ) -> ClarificationResult:
        payload = model_dump_compat(spec)
        modified = False
        questions: List[str] = []

        if not payload.get("description"):
            payload["description"] = (requirements_text or "Compiled workflow").strip()[:240]
            modified = True

        for step in payload.get("steps", []):
            if step["type"] == "tool" and not (
                step.get("config", {}).get("tool_name")
                or step.get("config", {}).get("loader")
            ):
                step.setdefault("config", {})
                step["config"]["tool_name"] = "passthrough"
                modified = True
                questions.append(
                    f"Step '{step['id']}' did not declare a tool; defaulted to passthrough."
                )

            if step["type"] == "llm":
                step.setdefault("config", {})
                if "temperature" not in step["config"]:
                    step["config"]["temperature"] = 0
                    modified = True
                if "model" not in step["config"]:
                    step["config"]["model"] = DWC_BEDROCK_MODEL_ID
                    modified = True

            step["timeout_seconds"] = max(30, int(step.get("timeout_seconds", 30)))

        clarified = WorkflowSpec(**payload)
        validate_workflow_spec(clarified)

        if clarified.outputs:
            return ClarificationResult(spec=clarified, questions=questions, modified=modified)

        sinks = self.resolver.sinks(clarified)
        if not sinks:
            return ClarificationResult(spec=clarified, questions=questions, modified=modified)

        payload = model_dump_compat(clarified)
        payload["outputs"] = [
            {
                "id": "result",
                "name": "result",
                "data_type": "object",
                "source_step": sinks[0],
                "description": "Auto-inferred terminal output.",
            }
        ]
        final_spec = WorkflowSpec(**payload)
        validate_workflow_spec(final_spec)
        return ClarificationResult(
            spec=final_spec,
            questions=questions,
            modified=True,
        )
