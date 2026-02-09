"""
Execution-stage service for runtime execution, stability evaluation, and version registration.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from dwc.agents.evaluation_agent import EvaluationAgent, StabilityReport
from dwc.ir.spec_schema import WorkflowSpec
from dwc.ir.versioning import WorkflowVersionManager
from dwc.runtime.executor import ExecutionReport, WorkflowExecutor


class ExecutionStageResult(BaseModel):
    report: ExecutionReport
    stability: StabilityReport
    version: str
    performance: Dict[str, Any] = Field(default_factory=dict)


class ExecutionService:
    def __init__(
        self,
        *,
        executor: WorkflowExecutor,
        evaluator: EvaluationAgent,
        versioning: WorkflowVersionManager,
    ) -> None:
        self.executor = executor
        self.evaluator = evaluator
        self.versioning = versioning

    def execute_and_assess(
        self,
        *,
        execute: bool,
        spec: WorkflowSpec,
        optimized_spec: WorkflowSpec,
        generated_script_path: str,
        dependencies: List[str],
        script_args: List[str],
        tool_records: List[Any],
    ) -> ExecutionStageResult:
        if execute:
            report = self.executor.execute(
                workflow_name=optimized_spec.name,
                script_path=generated_script_path,
                script_args=script_args,
                dependencies=dependencies,
                iteration=0,
            )
        else:
            report = ExecutionReport(
                success=False,
                logs="Execution skipped (--no-execute).",
                errors=None,
                latency_ms=0,
                resource_usage={},
                iteration=0,
            )

        stability = self.evaluator.evaluate([report], min_success_streak=1)
        if not execute:
            stability = StabilityReport(
                stable=False,
                reason="Execution skipped, artifact not eligible for stable versioning.",
                metrics=stability.metrics,
            )

        performance = {
            "tool_records": [self._dump_model(row) for row in tool_records],
            "stability": self._dump_model(stability),
            "execution_report": self._dump_model(report),
        }

        version = optimized_spec.version
        if execute and report.success and stability.stable:
            record = self.versioning.register_stable_version(
                workflow_name=optimized_spec.name,
                spec=spec,
                optimized_spec=optimized_spec,
                generated_code_path=generated_script_path,
                performance=performance,
            )
            version = record.version

        return ExecutionStageResult(
            report=report,
            stability=stability,
            version=version,
            performance=performance,
        )

    @staticmethod
    def _dump_model(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()  # type: ignore[attr-defined]
        if hasattr(value, "dict"):
            return value.dict()  # type: ignore[attr-defined]
        return value
