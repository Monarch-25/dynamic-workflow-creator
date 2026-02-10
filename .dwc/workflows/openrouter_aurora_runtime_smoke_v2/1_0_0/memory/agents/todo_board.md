# Agent To-Do Board

_run: openrouter_aurora_runtime_smoke_v2_
_updated: 2026-02-09T21:16:16.521272+00:00_

## planner_agent
- [x] `capture_intent`: Capture intent summary
  - latest: Using caller-provided intent summary.
- [x] `resolve_plan`: Resolve approved plan
  - latest: Using caller-provided approved plan.

## subtask_agent
- [x] `split_subtasks`: Split request into executable subtasks
  - latest: Created 8 subtask(s).

## tool_builder_agent
- [x] `build_tools`: Generate tool code candidates and select one per subtask
  - latest: Selected 8 tool(s); 8 passed verifier.

## tool_verifier_agent
- [x] `verify_tools`: Run sandboxed verification checks for tool candidates
  - latest: All verifier checks passed (8/8).

## synthesis_agent
- [x] `build_synthesis_prompt`: Build synthesis prompt for final LLM step
  - latest: Synthesis prompt ready.

## spec_service
- [x] `assemble_spec`: Build workflow spec from plan/subtasks/tools
  - latest: Spec assembled with 9 step(s).

## optimizer_agent
- [x] `optimize_spec`: Optimize workflow spec for execution
  - latest: Optimization complete.

## codegen_agent
- [x] `generate_artifacts`: Generate workflow.py/tools.py/spec.json/README
  - latest: Generated artifacts at .dwc/workflows/openrouter_aurora_runtime_smoke_v2/1_0_0.

## execution_service
- [ ] `execute_workflow`: Run compile-time execution check
  - latest: Execution disabled (--no-execute).

## evaluation_agent
- [ ] `assess_stability`: Evaluate execution stability metrics

## versioning_service
- [ ] `register_stable_version`: Register stable version when eligible
