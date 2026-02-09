"""
Validation and normalization utilities for WorkflowSpec.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from dwc.ir.spec_schema import EdgeSpec, StepSpec, WorkflowSpec, model_dump_compat


class SpecValidationError(ValueError):
    """Raised when a workflow spec fails semantic validation."""


def _build_graph(spec: WorkflowSpec) -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = {step.id: set() for step in spec.steps}
    for edge in spec.edges:
        graph.setdefault(edge.source, set()).add(edge.target)
        graph.setdefault(edge.target, set())
    return graph


def _topological_order(spec: WorkflowSpec) -> List[str]:
    graph = _build_graph(spec)
    in_degree: Dict[str, int] = {node: 0 for node in graph}
    for source, targets in graph.items():
        for target in targets:
            in_degree[target] += 1

    queue = deque(sorted(node for node, degree in in_degree.items() if degree == 0))
    order: List[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in sorted(graph[node]):
            in_degree[target] -= 1
            if in_degree[target] == 0:
                queue.append(target)

    if len(order) != len(graph):
        raise SpecValidationError("Workflow graph contains a cycle.")
    return order


def validate_workflow_spec(spec: WorkflowSpec) -> WorkflowSpec:
    if not spec.steps:
        raise SpecValidationError("Workflow must include at least one step.")

    step_ids = [step.id.strip() for step in spec.steps]
    if len(step_ids) != len(set(step_ids)):
        raise SpecValidationError("Step IDs must be unique.")
    if any(not step_id for step_id in step_ids):
        raise SpecValidationError("Step IDs cannot be empty.")

    step_id_set = set(step_ids)
    for edge in spec.edges:
        if edge.source not in step_id_set:
            raise SpecValidationError(f"Edge source does not exist: {edge.source}")
        if edge.target not in step_id_set:
            raise SpecValidationError(f"Edge target does not exist: {edge.target}")

    for output in spec.outputs:
        if output.source_step and output.source_step not in step_id_set:
            raise SpecValidationError(
                f"Output '{output.id}' references unknown step: {output.source_step}"
            )

    for step in spec.steps:
        if step.type == "tool" and not (
            step.config.get("tool_name") or step.config.get("loader")
        ):
            raise SpecValidationError(
                f"Tool step '{step.id}' must declare config.tool_name or config.loader."
            )
        if step.timeout_seconds <= 0:
            raise SpecValidationError(
                f"Step '{step.id}' timeout_seconds must be positive."
            )

    order = _topological_order(spec)
    if len(order) == 0:
        raise SpecValidationError("Workflow graph is empty after validation.")

    return spec


def normalize_workflow_spec(spec: WorkflowSpec) -> WorkflowSpec:
    """Create canonical ordering for deterministic serialization and codegen."""

    payload = model_dump_compat(spec)
    payload["inputs"] = sorted(payload.get("inputs", []), key=lambda item: item["id"])
    payload["outputs"] = sorted(payload.get("outputs", []), key=lambda item: item["id"])
    payload["steps"] = sorted(payload.get("steps", []), key=lambda item: item["id"])
    payload["edges"] = sorted(
        payload.get("edges", []),
        key=lambda item: (item["source"], item["target"], item.get("condition") or ""),
    )
    if payload.get("constraints"):
        payload["constraints"] = sorted(
            payload["constraints"], key=lambda item: item.get("id", "")
        )

    normalized = WorkflowSpec(**payload)
    validate_workflow_spec(normalized)
    return normalized


def select_terminal_steps(spec: WorkflowSpec) -> List[str]:
    """Return the steps that contribute to workflow outputs."""

    if spec.outputs:
        explicit = [out.source_step for out in spec.outputs if out.source_step]
        if explicit:
            return sorted(set(explicit))

    outgoing: Dict[str, int] = {step.id: 0 for step in spec.steps}
    for edge in spec.edges:
        outgoing[edge.source] += 1
    sinks = [step_id for step_id, count in outgoing.items() if count == 0]
    return sorted(sinks)


def create_spec(
    *,
    base: WorkflowSpec,
    steps: List[StepSpec],
    edges: List[EdgeSpec],
) -> WorkflowSpec:
    payload = model_dump_compat(base)
    payload["steps"] = [model_dump_compat(step) for step in steps]
    payload["edges"] = [model_dump_compat(edge) for edge in edges]
    return WorkflowSpec(**payload)
