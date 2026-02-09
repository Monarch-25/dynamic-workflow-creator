"""
Workflow execution orchestration in isolated sandbox.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dwc.runtime.sandbox import SandboxConfig, VenvSandbox
from dwc.runtime.state_store import ExecutionState, InMemoryStateStore
from dwc.runtime.telemetry import TelemetryCollector


class ExecutionReport(BaseModel):
    success: bool
    logs: str
    errors: Optional[str]
    latency_ms: int
    resource_usage: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    iteration: int = 0


class WorkflowExecutorConfig(BaseModel):
    install_dependencies: bool = True
    timeout_seconds: int = 180
    default_dependencies: List[str] = Field(
        default_factory=lambda: ["pydantic>=2.0.0"]
    )


class WorkflowExecutor:
    def __init__(
        self,
        *,
        sandbox: Optional[VenvSandbox] = None,
        telemetry: Optional[TelemetryCollector] = None,
        state_store: Optional[InMemoryStateStore] = None,
        config: Optional[WorkflowExecutorConfig] = None,
    ) -> None:
        self.config = config or WorkflowExecutorConfig()
        self.telemetry = telemetry or TelemetryCollector()
        self.state_store = state_store or InMemoryStateStore()
        self.sandbox = sandbox or VenvSandbox(
            SandboxConfig(timeout_seconds=self.config.timeout_seconds)
        )

    def execute(
        self,
        *,
        workflow_name: str,
        script_path: str,
        input_payload: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        iteration: int = 0,
    ) -> ExecutionReport:
        trace_id = self.telemetry.start_trace(workflow_name)
        self.state_store.set(
            ExecutionState(
                trace_id=trace_id,
                workflow_name=workflow_name,
                status="running",
                iteration=iteration,
            )
        )
        self.telemetry.log(
            trace_id, "execution_started", workflow_name=workflow_name, iteration=iteration
        )

        session = self.sandbox.create_session(workflow_name)
        try:
            if self.config.install_dependencies:
                deps = list(self.config.default_dependencies)
                if dependencies:
                    deps.extend(dependencies)
                deduped = sorted(set(deps))
                self.telemetry.log(trace_id, "dependency_install_started", deps=deduped)
                self.sandbox.install_requirements(session, deduped)
                self.telemetry.log(trace_id, "dependency_install_completed", deps=deduped)

            result = self.sandbox.run_script(
                session=session,
                script_path=script_path,
                input_payload=input_payload,
            )
            success = result.exit_code == 0
            report = ExecutionReport(
                success=success,
                logs=result.stdout.strip(),
                errors=result.stderr.strip() or None,
                latency_ms=result.duration_ms,
                resource_usage={"memory_kb": result.memory_kb},
                trace_id=trace_id,
                iteration=iteration,
            )
            self.state_store.update(
                trace_id,
                status="success" if success else "failed",
                iteration=iteration,
                payload=report.model_dump() if hasattr(report, "model_dump") else report.dict(),
            )
            self.telemetry.log(
                trace_id,
                "execution_completed",
                success=success,
                latency_ms=result.duration_ms,
                memory_kb=result.memory_kb,
            )
            return report
        except Exception as exc:
            report = ExecutionReport(
                success=False,
                logs="",
                errors=str(exc),
                latency_ms=0,
                resource_usage={},
                trace_id=trace_id,
                iteration=iteration,
            )
            self.state_store.update(
                trace_id,
                status="failed",
                iteration=iteration,
                payload=report.model_dump() if hasattr(report, "model_dump") else report.dict(),
            )
            self.telemetry.log(trace_id, "execution_failed", error=str(exc))
            return report
        finally:
            self.sandbox.cleanup(session)
