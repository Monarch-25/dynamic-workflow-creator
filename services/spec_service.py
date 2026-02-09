"""
Spec-stage service for WorkflowSpec assembly and execution input preparation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from dwc.ir.spec_schema import EdgeSpec, InputSpec, OutputSpec, StepSpec, WorkflowSpec
from dwc.ir.versioning import normalize_workflow_name
from dwc.llm import DWC_BEDROCK_MODEL_ID


class SpecService:
    @staticmethod
    def requires_document(
        requirements_text: str, subtasks: List[Dict[str, str]]
    ) -> bool:
        corpus = requirements_text.lower() + " " + " ".join(
            subtask["description"].lower() for subtask in subtasks
        )
        return any(
            token in corpus
            for token in ("doc", "document", "pdf", "docx", "extract code", "file")
        )

    def build_workflow_spec(
        self,
        *,
        workflow_name: Optional[str],
        requirements_text: str,
        approved_plan: str,
        intent_summary: str,
        current_task_description: str,
        subtasks: List[Dict[str, str]],
        tool_functions: Dict[str, Dict[str, str]],
        synthesis_prompt: str,
    ) -> WorkflowSpec:
        name = workflow_name or normalize_workflow_name(requirements_text[:60])
        requires_doc = self.requires_document(requirements_text, subtasks)

        steps: List[StepSpec] = []
        edges: List[EdgeSpec] = []
        for row in subtasks:
            steps.append(
                StepSpec(
                    id=row["id"],
                    type="tool",
                    config={
                        "tool_name": row["tool_name"],
                        "subtask_description": row["description"],
                    },
                    timeout_seconds=120,
                )
            )
            edges.append(EdgeSpec(source=row["id"], target="synthesize"))

        steps.append(
            StepSpec(
                id="synthesize",
                type="llm",
                config={
                    "model": DWC_BEDROCK_MODEL_ID,
                    "temperature": 0,
                    "prompt": synthesis_prompt,
                    "max_output_tokens": 1024,
                },
                timeout_seconds=120,
            )
        )

        inputs: List[InputSpec] = [
            InputSpec(
                id="query",
                name="query",
                data_type="string",
                required=False,
                description="Primary user question or request.",
            )
        ]
        if requires_doc:
            inputs.append(
                InputSpec(
                    id="doc",
                    name="doc",
                    data_type="document",
                    required=True,
                    description="Document content or path supplied via --doc.",
                )
            )

        metadata = {
            "architecture_mode": "subtask_tool_arsenal",
            "approved_plan": approved_plan,
            "intent_summary": intent_summary,
            "current_task_description": current_task_description,
            "subtasks": subtasks,
            "tool_functions": tool_functions,
            "synthesis_prompt": synthesis_prompt,
        }
        return WorkflowSpec(
            version="1.0.0",
            name=name,
            description=requirements_text.strip()[:300],
            inputs=inputs,
            outputs=[
                OutputSpec(
                    id="final_answer",
                    name="final_answer",
                    data_type="string",
                    source_step="synthesize",
                    description="Final plain-text answer.",
                )
            ],
            steps=steps,
            edges=edges,
            metadata=metadata,
        )

    @staticmethod
    def collect_dependencies(spec: WorkflowSpec, generated: List[str]) -> List[str]:
        deps = list(generated)
        extra = spec.metadata.get("extra_dependencies", [])
        if isinstance(extra, list):
            deps.extend(str(item) for item in extra)
        return sorted(set(deps))

    @staticmethod
    def build_execution_args(
        *,
        initial_state: Optional[Dict[str, Any]],
        requires_document: bool,
    ) -> List[str]:
        payload = dict(initial_state or {})
        if requires_document and not SpecService._payload_has_document(payload):
            payload["doc"] = (
                "Sample document content used for validation execution in compile step."
            )
        if payload:
            return ["--input-json", json.dumps(payload, sort_keys=True)]
        return []

    @staticmethod
    def _payload_has_document(payload: Dict[str, Any]) -> bool:
        candidate = payload.get("input", payload)
        if not isinstance(candidate, dict):
            return False
        return bool(
            candidate.get("doc")
            or candidate.get("document")
            or candidate.get("text")
            or candidate.get("doc_path")
        )
