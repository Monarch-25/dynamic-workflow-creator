# DWC Flow: User Request -> Workflow Creation -> Workflow Run

## 1. End-to-End Flow

```text
User Request
  -> Plan Generation (PlannerAgent)
  -> Subtask Decomposition (SubtaskAgent)
  -> Tool Build/Verify Loop (ToolBuilderAgent + ToolVerifierAgent)
  -> Workflow Spec Assembly (DynamicWorkflowCompiler)
  -> Spec Optimization (OptimizerAgent)
  -> Code Generation (CodegenAgent / LangGraphCodeGenerator)
  -> Optional Compile-Time Execution (WorkflowExecutor)
  -> Stability Evaluation + Version Registration
  -> User Runs Generated workflow.py with input
```

## 2. Step-by-Step Behavior

1. Request intake
- Source: CLI (`--requirements` / plan mode) or API (`POST /dwc/compile`).
- Requirements and context are persisted to markdown/vector memory.

2. Plan creation
- Planner generates a numbered plan and captures intent summary.
- In plan mode, user can iteratively refine before approval.

3. Subtask splitting
- Requirements are split into independent executable subtasks.
- Each subtask becomes a tool-construction unit.

4. Tool generation and verification
- Builder first checks deterministic built-ins (for example `code_search`, shell command wrapper with `safe_cli` approval).
- Before generation, tooling checks a shared reusable registry (`.dwc/memory/shared_tool_registry.json`) for similar verified tools and can try them first.
- If no built-in matches, a candidate function is generated for the subtask.
- Candidate runs in isolated virtualenv verifier harness.
- On failure, verifier feedback loops back into regeneration (bounded retries).
- Fallback tool is used if retries fail.
- Each tool attempt is persisted to `tool_attempts` (SQLite) including code hash and verifier diagnostics.
- Similar past failures are retrieved and distilled into guidance for subsequent tool-build prompts.
- Successful and failed attempts also update the shared tool registry so future runs can bootstrap missing tools faster.

5. Workflow spec synthesis
- Compiler creates `WorkflowSpec` with tool steps + final synthesis LLM step.
- Spec includes metadata: plan, intent summary, subtasks, tool source, synthesis prompt.

6. Optimization and code generation
- Validation/normalization/dependency analysis/parallel annotations/cost estimate.
- Generator emits `workflow.py`, `tools.py`, `README.md`, `spec.json`, memory snapshot.

7. Optional compile-time execution
- Generated workflow can be executed immediately to validate operability.
- Dependencies are installed in sandbox venv before execution.

8. Stability + versioning
- Execution report is evaluated for stability.
- Stable successful artifacts are registered in `.dwc/versions/<workflow>.json`.

9. Runtime invocation
- User runs generated `workflow.py` with `--query`, `--doc`, or JSON input.
- Subtasks execute in parallel; final synthesis combines outputs.

## 3. LLM Call Path in This Flow
Every LLM call is routed through:
- API: `langchain_aws.ChatBedrockConverse`
- Model ID: `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Shared config source: `dwc.llm`

This applies both during compile-time agent usage and generated workflow synthesis.
When available, planner/subtask/tool-builder use LangChain `bind_tools` for structured outputs; if unsupported, they fallback to plain `invoke` parsing.

## 4. Shortcomings Along the Flow

1. Plan/split/build stages can silently degrade to heuristic mode when LLM errors happen.
2. Verifier confirms contract compliance but may still approve logically weak tools.
3. Sandbox execution is isolated by virtualenv, not hard-isolated by container policy.
4. Generated runtime uses pragmatic parallel execution and synthesis, but not a full IR-policy executor.
5. Cost/latency prediction in optimization is approximate, not telemetry-calibrated.
6. LangChain tool-calling is only partially adopted; planner/subtask/tool-builder use `bind_tools` best-effort, while the rest of orchestration remains deterministic.
