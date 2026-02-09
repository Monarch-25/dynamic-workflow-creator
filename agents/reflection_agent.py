"""
Reflection agent for iterative repair via spec mutations.
"""

from __future__ import annotations

import re
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from dwc.ir.spec_schema import WorkflowSpec, model_dump_compat
from dwc.runtime.executor import ExecutionReport

ErrorClass = Literal[
    "SyntaxError",
    "ImportError",
    "RuntimeError",
    "TimeoutError",
    "SchemaViolation",
    "LogicalFailure",
]


class PatchAction(BaseModel):
    action: str
    target: str
    value: Any
    reason: str


class ReflectionResult(BaseModel):
    error_class: Optional[ErrorClass] = None
    actions: List[PatchAction] = Field(default_factory=list)
    patched_spec: Optional[WorkflowSpec] = None
    terminate: bool = False
    termination_reason: Optional[str] = None


class ReflectionAgent:
    def classify_error(self, report: ExecutionReport) -> ErrorClass:
        error_blob = "\n".join(filter(None, [report.errors or "", report.logs or ""]))
        lower = error_blob.lower()
        if "syntaxerror" in lower:
            return "SyntaxError"
        if "no module named" in lower or "importerror" in lower:
            return "ImportError"
        if "timeoutexpired" in lower or "timeout" in lower:
            return "TimeoutError"
        if "schema" in lower and ("invalid" in lower or "violation" in lower):
            return "SchemaViolation"
        if "assertionerror" in lower or "logical" in lower:
            return "LogicalFailure"
        return "RuntimeError"

    def reflect(
        self,
        *,
        spec: WorkflowSpec,
        generated_code_path: str,
        report: ExecutionReport,
        iteration: int,
        max_iterations: int,
    ) -> ReflectionResult:
        if report.success:
            return ReflectionResult(
                terminate=True,
                termination_reason="Execution succeeded.",
            )
        if iteration >= max_iterations - 1:
            return ReflectionResult(
                terminate=True,
                termination_reason="Reached max reflection iterations.",
            )

        error_class = self.classify_error(report)
        payload = model_dump_compat(spec)
        actions: List[PatchAction] = []

        if error_class == "ImportError":
            missing = self._missing_module_name(report.errors or "")
            if missing:
                payload.setdefault("metadata", {})
                deps = payload["metadata"].setdefault("extra_dependencies", [])
                package = self._map_module_to_package(missing)
                if package not in deps:
                    deps.append(package)
                    actions.append(
                        PatchAction(
                            action="add_dependency",
                            target="metadata.extra_dependencies",
                            value=package,
                            reason=f"Missing module detected: {missing}",
                        )
                    )
        elif error_class == "TimeoutError":
            for step in payload.get("steps", []):
                before = int(step.get("timeout_seconds", 60))
                step["timeout_seconds"] = min(900, max(before * 2, 60))
                actions.append(
                    PatchAction(
                        action="set_step_timeout",
                        target=f"steps.{step['id']}.timeout_seconds",
                        value=step["timeout_seconds"],
                        reason="Timeout detected; increasing timeout budget.",
                    )
                )
        elif error_class == "SchemaViolation":
            for step in payload.get("steps", []):
                if step.get("type") == "llm":
                    step.setdefault("config", {})
                    step["config"]["output_format"] = "json"
                    step["config"]["enforce_schema"] = True
                    actions.append(
                        PatchAction(
                            action="set_llm_schema_enforcement",
                            target=f"steps.{step['id']}.config",
                            value={"output_format": "json", "enforce_schema": True},
                            reason="Schema violation detected; forcing structured output.",
                        )
                    )
        else:
            for step in payload.get("steps", []):
                retry = step.setdefault("retry_policy", {})
                retry["max_retries"] = min(10, max(2, int(retry.get("max_retries", 1)) + 1))
                retry["backoff_strategy"] = "exponential"
                actions.append(
                    PatchAction(
                        action="increase_retries",
                        target=f"steps.{step['id']}.retry_policy.max_retries",
                        value=retry["max_retries"],
                        reason=f"{error_class} observed; increasing retries.",
                    )
                )

        if not actions:
            return ReflectionResult(
                error_class=error_class,
                terminate=True,
                termination_reason=(
                    "No safe patch action available for this error class. "
                    f"Generated code path: {generated_code_path}"
                ),
            )

        patched = WorkflowSpec(**payload)
        return ReflectionResult(
            error_class=error_class,
            actions=actions,
            patched_spec=patched,
            terminate=False,
        )

    @staticmethod
    def _missing_module_name(error_text: str) -> Optional[str]:
        match = re.search(r"No module named ['\"]([a-zA-Z0-9_.-]+)['\"]", error_text)
        return match.group(1) if match else None

    @staticmethod
    def _map_module_to_package(module_name: str) -> str:
        mapping = {
            "langgraph": "langgraph>=0.2.0",
            "langchain_aws": "langchain-aws>=0.2.0",
            "boto3": "boto3>=1.34.0",
            "pydantic": "pydantic>=2.0.0",
        }
        return mapping.get(module_name, module_name)
