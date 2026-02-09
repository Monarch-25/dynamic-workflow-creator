# DWC Orchestrator Contract

This document defines expected behavior for orchestration and component goals.
It is intentionally grep-friendly so each component can target its own section.

## ORCHESTRATOR_GOAL
- Convert user requirements into a verified executable workflow artifact.
- Prefer deterministic behavior when possible.
- Use Bedrock LLM calls via `langchain_aws.ChatBedrockConverse` when LLM is enabled.
- Keep fallback behavior observable (never silently swallow root-cause failures).

## ORCHESTRATOR_FLOW
1. Plan and intent extraction.
2. Subtask decomposition.
3. Tool generation + verification loop.
4. Workflow spec assembly.
5. Optimization and code generation.
6. Optional compile-time execution and stability assessment.
7. Persist history/memory/registry artifacts.

## SHARED_CONSTRAINTS
- All tool functions must return a dict with `tool`, `status`, and `result`.
- Non-destructive shell usage must go through `safe_cli`.
- Runtime generation must encode per-step timeout and retry policy.
- Graph topology must be generated from `WorkflowSpec.steps` and `WorkflowSpec.edges`, not hardcoded node names.
- On fallback to heuristic behavior, include explicit reason logging.

## AGENT_TARGET:planner_agent
- Input: requirements and optional refinement notes.
- Output: approved plan text and concise intent summary.
- Preferred mode: structured `bind_tools` extraction when supported.
- Fallback mode: plain `invoke` parsing, then deterministic heuristic plan/intent.
- Must log reason before fallback.

## AGENT_TARGET:subtask_agent
- Input: requirements + approved plan.
- Output: list of independent `SubtaskSpec` items with stable `id` and clear `description`.
- Preferred mode: structured `bind_tools` extraction.
- Fallback mode: plain `invoke` parsing, then heuristic split.
- Must cap subtasks using orchestrator-supplied `max_subtasks`.
- Must log reason before fallback.

## AGENT_TARGET:tool_builder_agent
- Input: one subtask, shared task description, optional verifier feedback.
- Output: `ToolCandidate` (`name`, `description`, `code`, `sample_input`, `origin`).
- Selection order:
1. deterministic built-in catalog
2. shared reusable tool registry candidate (if high confidence)
3. LLM-generated tool code
4. deterministic template fallback
- Must validate generated code and block banned patterns.
- Must log reason before fallback from LLM path.

## AGENT_TARGET:tool_verifier_agent
- Input: `ToolCandidate`.
- Output: `ToolVerificationResult` (`success`, `errors`, `output_preview`).
- Responsibilities:
1. execute candidate in isolated sandbox session
2. enforce output contract
3. provide actionable error text
- `safe_cli` prelude must not use `shell=True`.

## AGENT_TARGET:tooling_service
- Input: approved plan + requirements + current task description.
- Responsibilities:
1. split subtasks
2. build/verify each tool with bounded retries
3. persist attempts to history store
4. persist reusable contributions to shared registry
5. inject prior-failure guidance into retries
- Must always emit one usable tool per subtask (fallback allowed).

## AGENT_TARGET:spec_service
- Input: requirements, subtasks, tool functions, synthesis prompt.
- Output: `WorkflowSpec` with:
1. one step per subtask tool
2. final synthesis step
3. explicit edges
4. step `timeout_seconds` and `retry_policy`
- Must enforce Bedrock model id in LLM step config.

## AGENT_TARGET:langgraph_codegen
- Input: optimized `WorkflowSpec`.
- Output: generated `workflow.py`, `tools.py`, `README.md`, `spec.json`.
- Must:
1. generate graph nodes from all steps in spec
2. generate edges from spec edges
3. execute steps using per-step timeout/retry/backoff
4. preserve synthesis fallback when Bedrock unavailable
5. keep CLI/document input handling consistent

## AGENT_TARGET:synthesis_agent
- Input: requirements + approved plan + intent summary.
- Output: synthesis prompt text for final answer step.
- Preferred mode: LLM-generated concise synthesis prompt.
- Fallback mode: deterministic default synthesis prompt.
- Must log reason before fallback.

## AGENT_TARGET:execution_service
- Run generated workflow (optional mode).
- Evaluate stability and register version when stable.
- Persist execution reports and metadata.

## AGENT_TARGET:history_store
- Persist workflow history.
- Persist tool attempts for feedback and failure analysis.
- Support recent and similarity-based retrieval.

## AGENT_TARGET:shared_tool_registry
- Persist reusable tool code and contributor metadata.
- Provide high-confidence suggestion candidates only.
- Avoid self-reinforcing drift from registry-on-registry writes.

## OBSERVABILITY_REQUIREMENTS
- Fallback reason logging is mandatory for planner/subtask/tool-builder/synthesis/spec generation.
- Retry attempts and verifier outcomes are persisted.
- Shared registry contributions are persisted with contributor/source metadata.

