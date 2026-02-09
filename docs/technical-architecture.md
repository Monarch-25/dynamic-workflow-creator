# DWC Technical Architecture

## 1. System Purpose
DWC (Dynamic Workflow Compiler) converts natural-language workflow requests into executable LangGraph workflows with verifier-approved tool functions.

## 2. Top-Level Architecture

### Interfaces
- CLI entrypoint: `main.py`
- HTTP API entrypoint: `api/router.py`

### Orchestration Core
- `DynamicWorkflowCompiler` in `main.py` coordinates the full compile pipeline.
- It handles wiring and orchestration while stage logic is delegated to services.

### Stage Services
- `services/planning_service.py`: plan-mode loop + approved-plan/intent resolution.
- `services/tooling_service.py`: subtask decomposition and tool build/verify loop.
- `services/spec_service.py`: workflow spec assembly, dependency collection, execution-arg building.
- `services/execution_service.py`: compile-time execution, stability evaluation, and stable-version registration.

### Agent Layer
- `PlannerAgent`: creates/refines implementation plan and intent summary.
- `SubtaskAgent`: decomposes requirements into independent subtasks.
- `ToolBuilderAgent`: builds one Python function per subtask.
- `BuiltinToolCatalog`: deterministic tool selection layer used before LLM generation.
- `ToolVerifierAgent`: executes generated tools in a sandbox and validates output shape.
- `SynthesisAgent`: creates synthesis instructions for final answer generation.
- `OptimizerAgent`, `CodegenAgent`, `EvaluationAgent`: optimize spec, generate workflow files, and assess stability.

### IR + Compiler Layer
- Strongly-typed workflow IR: `ir/spec_schema.py` (`WorkflowSpec`, `StepSpec`, `EdgeSpec`, etc.).
- Validation + normalization: `ir/validators.py`.
- Optimization passes: `compiler/optimization_passes.py`.
- LangGraph/runtime code generation: `compiler/langgraph_codegen.py`.

### Runtime Layer
- `runtime/executor.py`: compile-time execution of generated workflows.
- `runtime/sandbox.py`: per-run virtualenv-based isolation.
- `runtime/telemetry.py` + `runtime/state_store.py`: trace and execution state.

### Persistence + Memory
- Markdown working memory: `memory/markdown_memory.py`.
- Lightweight vector memory: `memory/vector_store.py`.
- Compile/run history (SQLite): `memory/history_store.py`.
- Shared reusable tool registry: `memory/shared_tool_registry.py` persists verifier outcomes and reusable tool code snapshots in `.dwc/memory/shared_tool_registry.json`.
- Stable version registry: `ir/versioning.py`.
- Tool-attempt telemetry table: `tool_attempts` in `.dwc/memory/history.db` stores per-attempt tool calls, verifier outcomes, error class, snippets, and code hash.

## 3. LLM Architecture Standard
All in-app LLM calls are standardized on AWS Bedrock Converse via `langchain_aws.ChatBedrockConverse`.

- Shared model constant: `dwc.llm.DWC_BEDROCK_MODEL_ID`
- Fixed model ID: `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Shared factory: `dwc.llm.build_chat_bedrock_converse()`

Where this is applied:
- Compiler-side agent LLM client initialization in `main.py`.
- Spec defaults in `agents/spec_generator.py` and `agents/clarification_agent.py`.
- Generated workflow synthesis node in `compiler/langgraph_codegen.py`.
- Planner, subtask, and tool-builder agents now attempt structured tool binding (`bind_tools`) when the runtime LLM adapter supports it, and gracefully fallback to deterministic parsing when unavailable.

## 4. Built-In Tooling
- `agents/tool_catalog.py` introduces deterministic built-ins that bypass LLM code generation.
- Built-ins:
- grep/ripgrep-style `code_search` for Python/codebase search tasks.
- `shell_command` pattern tool that routes command execution through `safe_cli` with user approval controls (`execute` / `modify` / `skip`).
- Runtime behavior: prefer `rg` when available; fallback to safe Python scanning when unavailable.

## 5. Artifact Model
A successful compile emits:
- `workflow.py`: generated runtime graph
- `tools.py`: generated verifier-approved tool arsenal
- `spec.json`: compiled and optimized workflow spec
- `README.md`: runbook for generated workflow
- `memory/`: snapshot of current-task and agent working memory

Root location: `.dwc/workflows/<workflow_name>/<version>/`

## 6. Current Shortcomings

1. Error handling suppresses root causes in multiple agent LLM paths.
- Several agents use broad `except Exception: pass` and silently fall back to heuristics, which makes debugging model or prompt issues hard.

2. Sandbox isolation is partial, not container-grade.
- `VenvSandbox` isolates dependencies but is still process-level. The code itself notes that full filesystem/network isolation requires stronger host controls.

3. Tool verification checks interface integrity more than semantic correctness.
- Verifier asserts output structure (`status`, `result`) and sample execution success, but does not deeply validate correctness against requirements.

4. Generated tool CLI helper is safer now but still policy-limited.
- `safe_cli` now requires approval (`execute | modify:<command> | skip`), blocks shell metacharacters, and runs with `shell=False`.
- It still relies on string-command policy checks (denylist + token blocking), which is weaker than full command allowlisting or capability-scoped execution.

5. Runtime does not fully execute IR retry semantics at graph-node level.
- Retry policies are encoded in spec/metadata, but generated runtime execution path is not yet a full policy-driven step executor.

6. Cost estimation is coarse.
- Token and price estimates in optimization are static heuristics and may not reflect real Bedrock billing behavior.

7. LLM dependency fallback can change behavior significantly.
- If Bedrock client initialization fails, the system falls back to deterministic heuristics, which is useful for resilience but reduces output quality consistency.

8. LangChain tool-calling coverage is partial.
- Planner/subtask/tool-builder stages attempt `bind_tools`, but broader orchestration (retry loop/runtime execution) still runs via deterministic Python control flow instead of a full tool-call loop.

9. Failure-guidance retrieval is currently lexical and lightweight.
- Similarity is token/Jaccard-based over subtask text; no semantic embedding retrieval or learned ranking is applied yet.
