"""
Dynamic Workflow Compiler (DWC) orchestration entrypoint.

Simplified journey:
- Optional plan mode (interactive)
- Subtask split
- Tool build + venv verification loop
- LangGraph workflow generation
- Optional sandbox execution
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dwc.agents.codegen_agent import CodegenAgent
from dwc.agents.evaluation_agent import EvaluationAgent
from dwc.agents.optimizer_agent import OptimizerAgent
from dwc.agents.planner_agent import PlanResult, PlannerAgent
from dwc.agents.spec_generator import LLMProtocol
from dwc.agents.subtask_agent import SubtaskAgent
from dwc.agents.synthesis_agent import SynthesisAgent
from dwc.agents.tool_builder_agent import ToolBuilderAgent
from dwc.agents.tool_verifier_agent import ToolVerifierAgent
from dwc.ir.spec_schema import model_dump_compat
from dwc.ir.versioning import WorkflowVersionManager, normalize_workflow_name
from dwc.llm import build_chat_bedrock_converse
from dwc.memory.agent_todo_board import AgentTodoBoard
from dwc.memory.history_store import HistoryStore
from dwc.memory.markdown_memory import MarkdownMemoryStore
from dwc.memory.shared_tool_registry import SharedToolRegistry
from dwc.memory.vector_store import LocalVectorStore
from dwc.runtime.executor import WorkflowExecutor
from dwc.services import ExecutionService, PlanningService, SpecService, ToolingService

LOGGER = logging.getLogger(__name__)


class CompilationArtifact(BaseModel):
    workflow_name: str
    version: str
    created_at: str
    requirements_text: str
    approved_plan: str
    intent_summary: str
    plan_iterations: int = 1
    spec: Dict[str, Any]
    optimized_spec: Dict[str, Any]
    generated_script_path: str
    workflow_dir: Optional[str] = None
    workflow_runbook_path: Optional[str] = None
    workflow_tools_path: Optional[str] = None
    requires_document: bool = False
    subtasks: List[Dict[str, Any]] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    execution_report: Optional[Dict[str, Any]] = None
    stable: bool = False
    stability: Dict[str, Any] = Field(default_factory=dict)


class DynamicWorkflowCompiler:
    def __init__(
        self,
        llm: Optional[LLMProtocol] = None,
        *,
        todo_stream: Optional[bool] = None,
    ) -> None:
        resolved_llm = llm or self._build_default_llm()
        self.llm = resolved_llm
        self.planner = PlannerAgent(llm=resolved_llm)
        self.subtask_agent = SubtaskAgent(llm=resolved_llm)
        self.tool_builder = ToolBuilderAgent(llm=resolved_llm)
        self.tool_verifier = ToolVerifierAgent()
        self.synthesis_agent = SynthesisAgent(llm=resolved_llm)

        self.optimizer = OptimizerAgent()
        self.codegen = CodegenAgent()
        self.executor = WorkflowExecutor()
        self.evaluator = EvaluationAgent()
        self.versioning = WorkflowVersionManager()

        self.vector_store = LocalVectorStore()
        self.history_store = HistoryStore()
        self.memory_store = MarkdownMemoryStore()
        self.todo_board = AgentTodoBoard(
            root_dir=str(self.memory_store.root_dir),
            emit_console=todo_stream,
        )
        self.shared_tool_registry = SharedToolRegistry()

        self.planning_service = PlanningService(
            self.planner,
            todo_board=self.todo_board,
        )
        self.tooling_service = ToolingService(
            subtask_agent=self.subtask_agent,
            tool_builder=self.tool_builder,
            tool_verifier=self.tool_verifier,
            memory_store=self.memory_store,
            history_store=self.history_store,
            shared_tool_registry=self.shared_tool_registry,
            todo_board=self.todo_board,
        )
        self.spec_service = SpecService()
        self.execution_service = ExecutionService(
            executor=self.executor,
            evaluator=self.evaluator,
            versioning=self.versioning,
            todo_board=self.todo_board,
        )

    @staticmethod
    def _build_default_llm() -> Optional[LLMProtocol]:
        try:
            return build_chat_bedrock_converse()
        except Exception as exc:
            LOGGER.warning("Default Bedrock client unavailable; using heuristic fallback mode: %s", exc)
            return None

    def _reset_todo_board(self, *, workflow_name: str, execute: bool) -> None:
        self.todo_board.begin_run(run_label=workflow_name)
        self.todo_board.seed_agent(
            "planner_agent",
            [
                ("resolve_plan", "Resolve approved plan"),
                ("capture_intent", "Capture intent summary"),
            ],
        )
        self.todo_board.seed_agent(
            "subtask_agent",
            [("split_subtasks", "Split request into executable subtasks")],
        )
        self.todo_board.seed_agent(
            "tool_builder_agent",
            [("build_tools", "Generate tool code candidates and select one per subtask")],
        )
        self.todo_board.seed_agent(
            "tool_verifier_agent",
            [("verify_tools", "Run sandboxed verification checks for tool candidates")],
        )
        self.todo_board.seed_agent(
            "synthesis_agent",
            [("build_synthesis_prompt", "Build synthesis prompt for final LLM step")],
        )
        self.todo_board.seed_agent(
            "spec_service",
            [("assemble_spec", "Build workflow spec from plan/subtasks/tools")],
        )
        self.todo_board.seed_agent(
            "optimizer_agent",
            [("optimize_spec", "Optimize workflow spec for execution")],
        )
        self.todo_board.seed_agent(
            "codegen_agent",
            [("generate_artifacts", "Generate workflow.py/tools.py/spec.json/README")],
        )
        self.todo_board.seed_agent(
            "execution_service",
            [("execute_workflow", "Run compile-time execution check")],
        )
        self.todo_board.seed_agent(
            "evaluation_agent",
            [("assess_stability", "Evaluate execution stability metrics")],
        )
        self.todo_board.seed_agent(
            "versioning_service",
            [("register_stable_version", "Register stable version when eligible")],
        )
        self.todo_board.add_check(
            "execution_service",
            "execute_workflow",
            "Execution enabled." if execute else "Execution disabled (--no-execute).",
        )

    def run_plan_mode(
        self, initial_requirements: Optional[str] = None, max_iterations: int = 6
    ) -> PlanResult:
        self.todo_board.begin_run(run_label="plan_mode")
        self.todo_board.seed_agent(
            "planner_agent",
            [
                ("interactive_plan", "Draft and refine plan with user feedback"),
                ("capture_intent", "Capture intent summary from approved plan"),
            ],
        )
        return self.planning_service.run_plan_mode(
            initial_requirements=initial_requirements,
            max_iterations=max_iterations,
        )

    def compile_from_nl(
        self,
        *,
        requirements_text: str,
        workflow_name: Optional[str] = None,
        approved_plan: Optional[str] = None,
        intent_summary: Optional[str] = None,
        plan_iterations: int = 1,
        execute: bool = True,
        max_tool_iterations: int = 4,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> CompilationArtifact:
        if max_tool_iterations < 1:
            raise ValueError("max_tool_iterations must be >= 1")

        resolved_workflow_name = workflow_name or normalize_workflow_name(requirements_text[:60])
        self._reset_todo_board(workflow_name=resolved_workflow_name, execute=execute)

        approved_plan, intent_summary = self.planning_service.resolve_plan(
            requirements_text=requirements_text,
            approved_plan=approved_plan,
            intent_summary=intent_summary,
        )
        current_task_description = self.planning_service.compose_current_task_description(
            requirements_text=requirements_text,
            approved_plan=approved_plan,
            intent_summary=intent_summary,
        )
        self.memory_store.set_current_task_description(current_task_description)
        self.vector_store.add(
            requirements_text,
            metadata={"workflow_name": workflow_name or "workflow", "type": "requirements"},
        )
        self.memory_store.append_agent_working_memory(
            "planner_agent",
            f"Approved plan captured.\n\n{approved_plan}",
        )

        tooling = self.tooling_service.build_verified_tools(
            workflow_name=resolved_workflow_name,
            requirements_text=requirements_text,
            approved_plan=approved_plan,
            current_task_description=current_task_description,
            max_subtasks=8,
            max_tool_iterations=max_tool_iterations,
        )
        subtask_rows = tooling.subtask_rows
        tool_functions = tooling.tool_functions
        tool_records = tooling.tool_records

        self.todo_board.start(
            "synthesis_agent",
            "build_synthesis_prompt",
            "Generating synthesis prompt.",
        )
        try:
            synthesis_prompt = self.synthesis_agent.synthesis_prompt(
                requirements_text=requirements_text,
                approved_plan=approved_plan,
                intent_summary=intent_summary,
            )
            self.todo_board.complete(
                "synthesis_agent",
                "build_synthesis_prompt",
                "Synthesis prompt ready.",
            )
        except Exception as exc:
            self.todo_board.fail(
                "synthesis_agent",
                "build_synthesis_prompt",
                f"Synthesis prompt failed: {exc}",
            )
            raise

        self.todo_board.start(
            "spec_service",
            "assemble_spec",
            "Building workflow specification.",
        )
        try:
            spec = self.spec_service.build_workflow_spec(
                workflow_name=workflow_name,
                requirements_text=requirements_text,
                approved_plan=approved_plan,
                intent_summary=intent_summary,
                current_task_description=current_task_description,
                subtasks=subtask_rows,
                tool_functions=tool_functions,
                synthesis_prompt=synthesis_prompt,
            )
            self.todo_board.complete(
                "spec_service",
                "assemble_spec",
                f"Spec assembled with {len(spec.steps)} step(s).",
            )
        except Exception as exc:
            self.todo_board.fail(
                "spec_service",
                "assemble_spec",
                f"Spec assembly failed: {exc}",
            )
            raise

        self.todo_board.start(
            "optimizer_agent",
            "optimize_spec",
            "Running optimization passes.",
        )
        try:
            optimized_spec = self.optimizer.optimize(spec)
            self.todo_board.complete(
                "optimizer_agent",
                "optimize_spec",
                "Optimization complete.",
            )
        except Exception as exc:
            self.todo_board.fail(
                "optimizer_agent",
                "optimize_spec",
                f"Optimization failed: {exc}",
            )
            raise

        self.todo_board.start(
            "codegen_agent",
            "generate_artifacts",
            "Generating workflow artifacts.",
        )
        try:
            codegen_result = self.codegen.generate(optimized_spec)
            self.todo_board.complete(
                "codegen_agent",
                "generate_artifacts",
                f"Generated artifacts at {codegen_result.workflow_dir}.",
            )
        except Exception as exc:
            self.todo_board.fail(
                "codegen_agent",
                "generate_artifacts",
                f"Code generation failed: {exc}",
            )
            raise
        self.memory_store.export_snapshot(codegen_result.workflow_dir)

        dependencies = self.spec_service.collect_dependencies(
            optimized_spec, codegen_result.requirements
        )
        script_args = self.spec_service.build_execution_args(
            initial_state=initial_state,
            requires_document=codegen_result.io_contract.requires_document,
        )
        execution_result = self.execution_service.execute_and_assess(
            execute=execute,
            spec=spec,
            optimized_spec=optimized_spec,
            generated_script_path=codegen_result.script_path,
            dependencies=dependencies,
            script_args=script_args,
            tool_records=tool_records,
        )
        report = execution_result.report
        stability = execution_result.stability
        version = execution_result.version

        created_at = datetime.now(timezone.utc).isoformat()
        artifact = CompilationArtifact(
            workflow_name=normalize_workflow_name(optimized_spec.name),
            version=version,
            created_at=created_at,
            requirements_text=requirements_text,
            approved_plan=approved_plan,
            intent_summary=intent_summary,
            plan_iterations=plan_iterations,
            spec=model_dump_compat(spec),
            optimized_spec=model_dump_compat(optimized_spec),
            generated_script_path=codegen_result.script_path,
            workflow_dir=codegen_result.workflow_dir,
            workflow_runbook_path=codegen_result.runbook_path,
            workflow_tools_path=codegen_result.tools_path,
            requires_document=codegen_result.io_contract.requires_document,
            subtasks=subtask_rows,
            tools=[row.model_dump() for row in tool_records],
            dependencies=dependencies,
            execution_report=(
                report.model_dump() if hasattr(report, "model_dump") else report.dict()
            ),
            stable=bool(execute and report.success and stability.stable),
            stability=(
                stability.model_dump()
                if hasattr(stability, "model_dump")
                else stability.dict()
            ),
        )

        self.history_store.add_record(
            workflow_name=artifact.workflow_name,
            version=artifact.version,
            status="success" if report.success else "failed",
            latency_ms=report.latency_ms,
            cost_estimate=optimized_spec.metadata.get("cost_estimate", {}).get(
                "estimated_total_usd"
            ),
            created_at=created_at,
            payload=artifact.model_dump()
            if hasattr(artifact, "model_dump")
            else artifact.dict(),
        )
        return artifact


def _read_requirements_text(text: Optional[str], file_path: Optional[str]) -> str:
    if text:
        return text
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    raise ValueError("Provide --requirements or --requirements-file, or use --plan-mode.")


def _load_input_payload(raw_json: Optional[str], json_file: Optional[str]) -> Dict[str, Any]:
    if raw_json:
        return json.loads(raw_json)
    if json_file:
        return json.loads(Path(json_file).read_text(encoding="utf-8"))
    return {}


def _render_artifact_summary(artifact: CompilationArtifact) -> str:
    lines = [
        f"Workflow '{artifact.workflow_name}' compiled.",
        f"Version: {artifact.version}",
        f"Folder: {artifact.workflow_dir or '-'}",
        f"Runbook: {artifact.workflow_runbook_path or '-'}",
        f"Entrypoint: python {artifact.generated_script_path}",
        f"Requires document: {'yes' if artifact.requires_document else 'no'}",
        f"Subtasks: {len(artifact.subtasks)}",
        f"Tools: {len(artifact.tools)}",
        f"Stable: {'yes' if artifact.stable else 'no'}",
    ]
    report = artifact.execution_report or {}
    if report:
        lines.append(f"Execution success: {report.get('success')}")
        if report.get("errors"):
            lines.append(f"Execution errors: {report.get('errors')}")
    return "\n".join(lines)


def _render_home_screen() -> str:
    lines = [
        "=" * 72,
        "Dynamic Workflow Compiler (DWC)",
        "Compile natural-language requirements into a verifier-approved workflow.",
        "",
        "Modes:",
        "  1) Plan mode",
        "     - Trigger: --plan-mode (or no --requirements / --requirements-file)",
        "     - Use when requirements need refinement before compile.",
        "  2) Direct compile mode",
        "     - Trigger: --requirements or --requirements-file",
        "     - Use when requirements are ready for immediate compile.",
        "",
        "Execution behavior:",
        "  - Default: compile and run generated workflow for a smoke check.",
        "  - --no-execute: compile only, skip execution.",
        "  - Live [todo] progress lines show agent completion checks during compile.",
        "  - Force progress stream: --todo-stream or disable with --no-todo-stream.",
        "",
        "Input options for execution payload:",
        "  - --input-json '<json>'",
        "  - --input-file /path/to/payload.json",
        "",
        "LLM standard:",
        "  - langchain_aws.ChatBedrockConverse",
        "  - model_id: us.anthropic.claude-sonnet-4-20250514-v1:0",
        "=" * 72,
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dynamic Workflow Compiler (DWC)")
    parser.add_argument("--requirements", type=str, default=None)
    parser.add_argument("--requirements-file", type=str, default=None)
    parser.add_argument("--workflow-name", type=str, default=None)
    parser.add_argument("--plan-mode", action="store_true")
    parser.add_argument("--max-plan-iterations", type=int, default=6)
    parser.add_argument("--max-tool-iterations", type=int, default=4)
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument("--input-json", type=str, default=None)
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--output-file", type=str, default=None)
    parser.add_argument("--no-home-screen", action="store_true")
    parser.add_argument("--todo-stream", action="store_true")
    parser.add_argument("--no-todo-stream", action="store_true")
    args = parser.parse_args()

    if args.todo_stream and args.no_todo_stream:
        raise ValueError("Choose either --todo-stream or --no-todo-stream, not both.")

    if not args.no_home_screen:
        print(_render_home_screen())

    todo_stream: Optional[bool] = None
    if args.todo_stream:
        todo_stream = True
    elif args.no_todo_stream:
        todo_stream = False

    compiler = DynamicWorkflowCompiler(todo_stream=todo_stream)
    initial_state = _load_input_payload(args.input_json, args.input_file)

    plan_mode_requested = args.plan_mode or (
        not args.requirements and not args.requirements_file
    )
    if plan_mode_requested:
        seed_requirements = None
        if args.requirements or args.requirements_file:
            seed_requirements = _read_requirements_text(
                args.requirements, args.requirements_file
            )
        plan = compiler.run_plan_mode(
            initial_requirements=seed_requirements,
            max_iterations=args.max_plan_iterations,
        )
        requirements_text = plan.requirements_text
        approved_plan = plan.proposed_plan
        intent_summary = plan.intent_summary
        plan_iterations = plan.iterations
    else:
        requirements_text = _read_requirements_text(args.requirements, args.requirements_file)
        approved_plan = compiler.planner.propose_plan(requirements_text)
        intent_summary = compiler.planner.capture_intent(requirements_text, approved_plan)
        plan_iterations = 1

    artifact = compiler.compile_from_nl(
        requirements_text=requirements_text,
        workflow_name=args.workflow_name,
        approved_plan=approved_plan,
        intent_summary=intent_summary,
        plan_iterations=plan_iterations,
        execute=not args.no_execute,
        max_tool_iterations=args.max_tool_iterations,
        initial_state=initial_state,
    )
    summary = _render_artifact_summary(artifact)
    print(summary)

    if args.output_file:
        payload = (
            artifact.model_dump()
            if hasattr(artifact, "model_dump")
            else artifact.dict()
        )
        Path(args.output_file).write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
