"""
Dynamic Workflow Compiler (DWC) orchestration entrypoint.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dwc.agents.clarification_agent import ClarificationAgent
from dwc.agents.codegen_agent import CodegenAgent
from dwc.agents.evaluation_agent import EvaluationAgent, StabilityReport
from dwc.agents.optimizer_agent import OptimizerAgent
from dwc.agents.reflection_agent import ReflectionAgent
from dwc.agents.spec_generator import LLMProtocol, SpecGeneratorAgent
from dwc.ir.spec_schema import WorkflowSpec, model_dump_compat
from dwc.ir.versioning import WorkflowVersionManager, normalize_workflow_name
from dwc.memory.history_store import HistoryStore
from dwc.memory.vector_store import LocalVectorStore
from dwc.runtime.executor import ExecutionReport, WorkflowExecutor


class CompilationArtifact(BaseModel):
    workflow_name: str
    version: str
    created_at: str
    requirements_text: str
    spec: Dict[str, Any]
    optimized_spec: Dict[str, Any]
    generated_script_path: str
    dependencies: List[str] = Field(default_factory=list)
    execution_report: Optional[Dict[str, Any]] = None
    reflection_iterations: int = 0
    stable: bool = False
    stability: Dict[str, Any] = Field(default_factory=dict)
    reflections: List[Dict[str, Any]] = Field(default_factory=list)


class DynamicWorkflowCompiler:
    def __init__(self, llm: Optional[LLMProtocol] = None) -> None:
        self.spec_generator = SpecGeneratorAgent(llm=llm)
        self.clarifier = ClarificationAgent()
        self.optimizer = OptimizerAgent()
        self.codegen = CodegenAgent()
        self.executor = WorkflowExecutor()
        self.reflection = ReflectionAgent()
        self.evaluator = EvaluationAgent()
        self.versioning = WorkflowVersionManager()
        self.vector_store = LocalVectorStore()
        self.history_store = HistoryStore()

    def compile_from_nl(
        self,
        *,
        requirements_text: str,
        workflow_name: Optional[str] = None,
        execute: bool = True,
        max_reflections: int = 5,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> CompilationArtifact:
        if max_reflections < 1:
            raise ValueError("max_reflections must be >= 1")

        spec = self.spec_generator.generate(requirements_text, workflow_name)
        clarification = self.clarifier.clarify(spec, requirements_text=requirements_text)
        current_spec = clarification.spec

        reports: List[ExecutionReport] = []
        reflections: List[Dict[str, Any]] = []
        optimized_spec: Optional[WorkflowSpec] = None
        generated_script_path = ""
        dependencies: List[str] = []

        self.vector_store.add(
            requirements_text,
            metadata={"workflow_name": current_spec.name, "type": "requirements"},
        )

        for iteration in range(max_reflections):
            optimized_spec = self.optimizer.optimize(current_spec)
            codegen_result = self.codegen.generate(optimized_spec)
            generated_script_path = codegen_result.script_path
            dependencies = self._collect_dependencies(optimized_spec, codegen_result.requirements)

            if execute:
                report = self.executor.execute(
                    workflow_name=optimized_spec.name,
                    script_path=generated_script_path,
                    input_payload=initial_state or {},
                    dependencies=dependencies,
                    iteration=iteration,
                )
            else:
                report = ExecutionReport(
                    success=True,
                    logs="Execution skipped (--no-execute).",
                    errors=None,
                    latency_ms=0,
                    resource_usage={},
                    iteration=iteration,
                )
            reports.append(report)
            if report.success:
                break

            reflection_result = self.reflection.reflect(
                spec=current_spec,
                generated_code_path=generated_script_path,
                report=report,
                iteration=iteration,
                max_iterations=max_reflections,
            )
            reflections.append(
                reflection_result.model_dump()
                if hasattr(reflection_result, "model_dump")
                else reflection_result.dict()
            )
            if reflection_result.terminate or reflection_result.patched_spec is None:
                break
            current_spec = reflection_result.patched_spec

        if optimized_spec is None:
            optimized_spec = self.optimizer.optimize(current_spec)

        stability: StabilityReport = self.evaluator.evaluate(
            reports, min_success_streak=1
        )
        if not execute:
            stability = StabilityReport(
                stable=False,
                reason="Execution skipped, artifact not eligible for stable versioning.",
                metrics=stability.metrics,
            )
        last_report = reports[-1] if reports else None

        created_at = datetime.now(timezone.utc).isoformat()
        stable = stability.stable
        version = optimized_spec.version
        if stable and generated_script_path:
            record = self.versioning.register_stable_version(
                workflow_name=optimized_spec.name,
                spec=current_spec,
                optimized_spec=optimized_spec,
                generated_code_path=generated_script_path,
                performance={
                    "stability": (
                        stability.model_dump()
                        if hasattr(stability, "model_dump")
                        else stability.dict()
                    ),
                    "latest_report": (
                        last_report.model_dump()
                        if (last_report and hasattr(last_report, "model_dump"))
                        else (last_report.dict() if last_report else {})
                    ),
                },
            )
            version = record.version

        artifact = CompilationArtifact(
            workflow_name=normalize_workflow_name(optimized_spec.name),
            version=version,
            created_at=created_at,
            requirements_text=requirements_text,
            spec=model_dump_compat(current_spec),
            optimized_spec=model_dump_compat(optimized_spec),
            generated_script_path=generated_script_path,
            dependencies=dependencies,
            execution_report=(
                last_report.model_dump()
                if (last_report and hasattr(last_report, "model_dump"))
                else (last_report.dict() if last_report else None)
            ),
            reflection_iterations=len(reflections),
            stable=stable,
            stability=(
                stability.model_dump()
                if hasattr(stability, "model_dump")
                else stability.dict()
            ),
            reflections=reflections,
        )

        if last_report:
            self.history_store.add_record(
                workflow_name=artifact.workflow_name,
                version=artifact.version,
                status="success" if last_report.success else "failed",
                latency_ms=last_report.latency_ms,
                cost_estimate=optimized_spec.metadata.get("cost_estimate", {}).get(
                    "estimated_total_usd"
                ),
                created_at=created_at,
                payload=artifact.model_dump()
                if hasattr(artifact, "model_dump")
                else artifact.dict(),
            )

        return artifact

    @staticmethod
    def _collect_dependencies(spec: WorkflowSpec, generated: List[str]) -> List[str]:
        deps = list(generated)
        extra = spec.metadata.get("extra_dependencies", [])
        if isinstance(extra, list):
            deps.extend(str(item) for item in extra)
        return sorted(set(deps))


def _read_requirements_text(text: Optional[str], file_path: Optional[str]) -> str:
    if text:
        return text
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    raise ValueError("Provide --requirements or --requirements-file.")


def _load_input_payload(raw_json: Optional[str], json_file: Optional[str]) -> Dict[str, Any]:
    if raw_json:
        return json.loads(raw_json)
    if json_file:
        return json.loads(Path(json_file).read_text(encoding="utf-8"))
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dynamic Workflow Compiler (DWC)")
    parser.add_argument("--requirements", type=str, default=None)
    parser.add_argument("--requirements-file", type=str, default=None)
    parser.add_argument("--workflow-name", type=str, default=None)
    parser.add_argument("--max-reflections", type=int, default=5)
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument("--input-json", type=str, default=None)
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--output-file", type=str, default=None)
    args = parser.parse_args()

    requirements_text = _read_requirements_text(args.requirements, args.requirements_file)
    input_payload = _load_input_payload(args.input_json, args.input_file)
    compiler = DynamicWorkflowCompiler()
    artifact = compiler.compile_from_nl(
        requirements_text=requirements_text,
        workflow_name=args.workflow_name,
        execute=not args.no_execute,
        max_reflections=args.max_reflections,
        initial_state=input_payload,
    )
    payload = artifact.model_dump() if hasattr(artifact, "model_dump") else artifact.dict()
    output = json.dumps(payload, indent=2, sort_keys=True)
    print(output)
    if args.output_file:
        Path(args.output_file).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
