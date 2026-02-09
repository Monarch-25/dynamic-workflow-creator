"""
Optimization pass pipeline for WorkflowSpec.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Dict, List, Optional, Set

from dwc.compiler.dependency_resolver import DependencyResolver
from dwc.ir.spec_schema import EdgeSpec, StepSpec, WorkflowSpec, model_dump_compat
from dwc.ir.validators import (
    SpecValidationError,
    normalize_workflow_spec,
    select_terminal_steps,
    validate_workflow_spec,
)


class OptimizationPass(ABC):
    name = "base"

    @abstractmethod
    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        raise NotImplementedError


class ValidatePass(OptimizationPass):
    name = "validate"

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        validate_workflow_spec(spec)
        return spec


class NormalizePass(OptimizationPass):
    name = "normalize"

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        return normalize_workflow_spec(spec)


class DependencyResolvePass(OptimizationPass):
    name = "dependency_resolve"

    def __init__(self) -> None:
        self.resolver = DependencyResolver()

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        payload = model_dump_compat(spec)
        payload.setdefault("metadata", {})
        payload["metadata"]["dependency"] = {
            "topological_order": self.resolver.topological_order(spec),
            "roots": self.resolver.roots(spec),
            "sinks": self.resolver.sinks(spec),
        }
        return WorkflowSpec(**payload)


class DeadStepEliminationPass(OptimizationPass):
    name = "dead_step_elimination"

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        if not spec.steps:
            return spec

        reverse: Dict[str, Set[str]] = {step.id: set() for step in spec.steps}
        for edge in spec.edges:
            reverse.setdefault(edge.target, set()).add(edge.source)
            reverse.setdefault(edge.source, set())

        terminals = select_terminal_steps(spec)
        if not terminals:
            return spec

        queue = deque(terminals)
        useful: Set[str] = set(terminals)
        while queue:
            node = queue.popleft()
            for parent in reverse.get(node, set()):
                if parent not in useful:
                    useful.add(parent)
                    queue.append(parent)

        retained_steps = [step for step in spec.steps if step.id in useful]
        retained_edges = [
            edge
            for edge in spec.edges
            if edge.source in useful and edge.target in useful
        ]

        payload = model_dump_compat(spec)
        payload["steps"] = [model_dump_compat(step) for step in retained_steps]
        payload["edges"] = [model_dump_compat(edge) for edge in retained_edges]
        payload["outputs"] = [
            output
            for output in payload.get("outputs", [])
            if not output.get("source_step") or output.get("source_step") in useful
        ]
        return WorkflowSpec(**payload)


class MergeCompatibleStepsPass(OptimizationPass):
    """
    Merge sequential LLM steps when configuration is equivalent.
    """

    name = "merge_compatible_steps"

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        step_by_id: Dict[str, StepSpec] = {step.id: step for step in spec.steps}
        incoming: Dict[str, List[EdgeSpec]] = {step.id: [] for step in spec.steps}
        outgoing: Dict[str, List[EdgeSpec]] = {step.id: [] for step in spec.steps}
        for edge in spec.edges:
            incoming.setdefault(edge.target, []).append(edge)
            outgoing.setdefault(edge.source, []).append(edge)

        merged_into: Dict[str, str] = {}
        removed_steps: Set[str] = set()

        for step in spec.steps:
            source_id = step.id
            if source_id in removed_steps:
                continue

            for edge in list(outgoing.get(source_id, [])):
                target_id = edge.target
                if target_id in removed_steps:
                    continue
                source = step_by_id[source_id]
                target = step_by_id[target_id]
                if edge.condition:
                    continue
                if source.type != "llm" or target.type != "llm":
                    continue
                if len(outgoing.get(source_id, [])) != 1:
                    continue
                if len(incoming.get(target_id, [])) != 1:
                    continue

                source_model = source.config.get("model")
                target_model = target.config.get("model")
                source_temp = source.config.get("temperature", 0)
                target_temp = target.config.get("temperature", 0)
                if source_model != target_model or source_temp != target_temp:
                    continue

                merged_prompt = []
                if "prompt" in source.config:
                    merged_prompt.append(str(source.config["prompt"]))
                if "prompt" in target.config:
                    merged_prompt.append(str(target.config["prompt"]))

                source_config = dict(source.config)
                if merged_prompt:
                    source_config["prompt"] = "\n\n".join(merged_prompt)
                source_config["fused_steps"] = [
                    source_id,
                    target_id,
                ]
                source_retry = source.retry_policy
                source_timeout = max(source.timeout_seconds, target.timeout_seconds)
                step_by_id[source_id] = StepSpec(
                    id=source.id,
                    type=source.type,
                    config=source_config,
                    retry_policy=source_retry,
                    timeout_seconds=source_timeout,
                )

                for target_edge in list(outgoing.get(target_id, [])):
                    outgoing[source_id].append(
                        EdgeSpec(
                            source=source_id,
                            target=target_edge.target,
                            condition=target_edge.condition,
                        )
                    )
                    incoming[target_edge.target] = [
                        EdgeSpec(
                            source=source_id if e.source == target_id else e.source,
                            target=e.target,
                            condition=e.condition,
                        )
                        for e in incoming.get(target_edge.target, [])
                    ]

                outgoing[source_id] = [
                    e for e in outgoing[source_id] if e.target != target_id
                ]
                incoming[target_id] = []
                outgoing[target_id] = []
                merged_into[target_id] = source_id
                removed_steps.add(target_id)

        if not removed_steps:
            return spec

        new_steps = [
            step_by_id[step.id] for step in spec.steps if step.id not in removed_steps
        ]
        new_edges: List[EdgeSpec] = []
        seen_edges: Set[str] = set()
        for source_id, edges in outgoing.items():
            if source_id in removed_steps:
                continue
            for edge in edges:
                target_id = merged_into.get(edge.target, edge.target)
                source_key = merged_into.get(edge.source, edge.source)
                if source_key == target_id:
                    continue
                key = f"{source_key}->{target_id}:{edge.condition or ''}"
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                new_edges.append(
                    EdgeSpec(source=source_key, target=target_id, condition=edge.condition)
                )

        payload = model_dump_compat(spec)
        payload["steps"] = [model_dump_compat(step) for step in new_steps]
        payload["edges"] = [model_dump_compat(edge) for edge in new_edges]
        for output in payload.get("outputs", []):
            source_step = output.get("source_step")
            if source_step in merged_into:
                output["source_step"] = merged_into[source_step]
        return WorkflowSpec(**payload)


class ParallelizationPass(OptimizationPass):
    name = "parallelization"

    def __init__(self) -> None:
        self.resolver = DependencyResolver()

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        groups = self.resolver.find_parallel_groups(spec)
        if not groups:
            return spec

        payload = model_dump_compat(spec)
        payload.setdefault("metadata", {})
        payload["metadata"]["parallel_groups"] = groups
        group_index: Dict[str, int] = {}
        for idx, group in enumerate(groups):
            for step_id in group:
                group_index[step_id] = idx

        for step in payload["steps"]:
            if step["id"] in group_index:
                step.setdefault("config", {})
                step["config"]["parallel_group"] = f"group_{group_index[step['id']]}"
        return WorkflowSpec(**payload)


class RetryPolicyInjectionPass(OptimizationPass):
    name = "retry_policy_injection"

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        payload = model_dump_compat(spec)
        for step in payload["steps"]:
            retry = step.get("retry_policy", {})
            step_type = step["type"]
            if step_type == "llm":
                retry["max_retries"] = max(2, int(retry.get("max_retries", 0)))
                retry["backoff_strategy"] = retry.get(
                    "backoff_strategy", "exponential"
                )
            elif step_type == "tool":
                retry["max_retries"] = max(1, int(retry.get("max_retries", 0)))
                retry["backoff_strategy"] = retry.get("backoff_strategy", "fixed")
            else:
                retry["max_retries"] = max(1, int(retry.get("max_retries", 1)))
                retry["backoff_strategy"] = retry.get("backoff_strategy", "fixed")

            retry.setdefault("initial_delay_seconds", 1.0)
            retry.setdefault("max_delay_seconds", 30.0)
            step["retry_policy"] = retry
            step["timeout_seconds"] = max(30, step.get("timeout_seconds", 30))
        return WorkflowSpec(**payload)


class CostEstimationPass(OptimizationPass):
    name = "cost_estimation"

    def apply(self, spec: WorkflowSpec) -> WorkflowSpec:
        llm_steps = [step for step in spec.steps if step.type == "llm"]
        estimated_input_tokens = 0
        estimated_output_tokens = 0

        for step in llm_steps:
            prompt = str(step.config.get("prompt", ""))
            prompt_tokens = max(1, len(prompt) // 4)
            response_tokens = int(step.config.get("max_output_tokens", 512))
            estimated_input_tokens += prompt_tokens
            estimated_output_tokens += response_tokens

        # Conservative default estimate for Claude-like pricing:
        # $0.003 / 1k input tokens, $0.015 / 1k output tokens
        input_cost = (estimated_input_tokens / 1000.0) * 0.003
        output_cost = (estimated_output_tokens / 1000.0) * 0.015

        payload = model_dump_compat(spec)
        payload.setdefault("metadata", {})
        payload["metadata"]["cost_estimate"] = {
            "llm_steps": len(llm_steps),
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_total_usd": round(input_cost + output_cost, 6),
        }
        return WorkflowSpec(**payload)


class Optimizer:
    def __init__(self, passes: Optional[List[OptimizationPass]] = None) -> None:
        self.passes = passes or [
            ValidatePass(),
            NormalizePass(),
            DependencyResolvePass(),
            DeadStepEliminationPass(),
            MergeCompatibleStepsPass(),
            ParallelizationPass(),
            RetryPolicyInjectionPass(),
            CostEstimationPass(),
        ]

    def optimize(self, spec: WorkflowSpec) -> WorkflowSpec:
        current = spec
        trace: List[str] = []
        for optimization_pass in self.passes:
            try:
                current = optimization_pass.apply(current)
                trace.append(optimization_pass.name)
            except SpecValidationError:
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"Optimization pass '{optimization_pass.name}' failed: {exc}"
                ) from exc

        payload = model_dump_compat(current)
        payload.setdefault("metadata", {})
        payload["metadata"]["optimization_trace"] = trace
        return WorkflowSpec(**payload)
