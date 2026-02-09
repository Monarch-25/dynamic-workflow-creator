# Agent To-Do Board

_run: smoke_todo_stream_
_updated: 2026-02-09T20:10:21.905544+00:00_

## planner_agent
- [x] `capture_intent`: Capture intent summary
  - latest: Generated intent summary.
- [x] `resolve_plan`: Resolve approved plan
  - latest: Generated approved plan.

## subtask_agent
- [x] `split_subtasks`: Split request into executable subtasks
  - latest: Created 1 subtask(s).

## tool_builder_agent
- [x] `build_tools`: Generate tool code candidates and select one per subtask
  - latest: Selected 1 tool(s); 1 passed verifier.

## tool_verifier_agent
- [x] `verify_tools`: Run sandboxed verification checks for tool candidates
  - latest: All verifier checks passed (1/1).

## synthesis_agent
- [x] `build_synthesis_prompt`: Build synthesis prompt for final LLM step
  - latest: Synthesis prompt ready.

## spec_service
- [x] `assemble_spec`: Build workflow spec from plan/subtasks/tools
  - latest: Spec assembled with 2 step(s).

## optimizer_agent
- [x] `optimize_spec`: Optimize workflow spec for execution
  - latest: Optimization complete.

## codegen_agent
- [x] `generate_artifacts`: Generate workflow.py/tools.py/spec.json/README
  - latest: Generated artifacts at .dwc/workflows/smoke_todo_stream/1_0_0.

## execution_service
- [ ] `execute_workflow`: Run compile-time execution check
  - latest: Execution disabled (--no-execute).

## evaluation_agent
- [ ] `assess_stability`: Evaluate execution stability metrics

## versioning_service
- [ ] `register_stable_version`: Register stable version when eligible
