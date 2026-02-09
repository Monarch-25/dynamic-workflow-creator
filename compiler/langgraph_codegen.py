"""
LangGraph code generation from optimized WorkflowSpec.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dwc.compiler.dependency_resolver import DependencyResolver
from dwc.ir.spec_schema import WorkflowSpec, model_dump_compat


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_") or "workflow"


def _safe_identifier(value: str) -> str:
    candidate = _safe_name(value)
    if candidate and candidate[0].isdigit():
        candidate = f"step_{candidate}"
    return candidate


class CodegenResult(BaseModel):
    script_path: str
    requirements: List[str] = Field(default_factory=list)
    entrypoint: str = "run_workflow"


class LangGraphCodeGenerator:
    def __init__(self, output_dir: str = ".dwc/generated") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.resolver = DependencyResolver()

    def generate(
        self, spec: WorkflowSpec, filename: Optional[str] = None
    ) -> CodegenResult:
        safe_name = _safe_name(spec.name)
        safe_version = _safe_name(spec.version)
        filename = filename or f"{safe_name}_{safe_version}.py"
        script_path = self.output_dir / filename
        script_path.write_text(self.render(spec), encoding="utf-8")
        return CodegenResult(
            script_path=str(script_path),
            requirements=[
                "langgraph>=0.2.0",
                "langchain-aws>=0.2.0",
                "boto3>=1.34.0",
            ],
            entrypoint="run_workflow",
        )

    def render(self, spec: WorkflowSpec) -> str:
        step_configs: Dict[str, Dict[str, Any]] = {
            step.id: step.config for step in spec.steps
        }
        step_types: Dict[str, str] = {step.id: step.type for step in spec.steps}
        timeout_map: Dict[str, int] = {step.id: step.timeout_seconds for step in spec.steps}
        retry_map: Dict[str, Dict[str, Any]] = {
            step.id: model_dump_compat(step.retry_policy) for step in spec.steps
        }
        output_bindings: Dict[str, List[str]] = {}
        for output in spec.outputs:
            if output.source_step:
                output_bindings.setdefault(output.source_step, []).append(output.name)

        roots = self.resolver.roots(spec)
        sinks = self.resolver.sinks(spec)
        edge_groups: Dict[str, List[Dict[str, Any]]] = {}
        for edge in spec.edges:
            edge_groups.setdefault(edge.source, []).append(
                {"target": edge.target, "condition": edge.condition}
            )

        node_defs: List[str] = []
        add_node_lines: List[str] = []
        for step in spec.steps:
            func_name = f"node_{_safe_identifier(step.id)}"
            node_defs.append(
                (
                    f"def {func_name}(state: WorkflowState) -> Dict[str, Any]:\n"
                    f"    return _execute_step("
                    f"step_id={json.dumps(step.id)}, "
                    f"step_type={json.dumps(step.type)}, "
                    f"state=state"
                    f")\n"
                )
            )
            add_node_lines.append(
                f'builder.add_node({json.dumps(step.id)}, {func_name})'
            )

        routing_defs: List[str] = []
        edge_lines: List[str] = []
        for source, edges in sorted(edge_groups.items()):
            conditional_edges = [edge for edge in edges if edge["condition"]]
            default_edges = [edge for edge in edges if not edge["condition"]]

            if conditional_edges:
                route_name = f"route_from_{_safe_identifier(source)}"
                route_lines = [
                    f"def {route_name}(state: WorkflowState) -> str:",
                    f"    last_output = state.get('step_results', {{}}).get({json.dumps(source)})",
                ]
                for edge in conditional_edges:
                    route_lines.append(
                        "    if _eval_condition("
                        + f"{json.dumps(edge['condition'])}, state, last_output):"
                    )
                    route_lines.append(f"        return {json.dumps(edge['target'])}")
                if default_edges:
                    route_lines.append(
                        f"    return {json.dumps(default_edges[0]['target'])}"
                    )
                else:
                    route_lines.append('    return "__end__"')
                routing_defs.append("\n".join(route_lines))

                mapping_entries = {
                    edge["target"]: edge["target"] for edge in conditional_edges
                }
                if default_edges:
                    mapping_entries[default_edges[0]["target"]] = default_edges[0]["target"]
                mapping_entries["__end__"] = "END"
                mapping_literal_parts = []
                for key, value in mapping_entries.items():
                    if value == "END":
                        mapping_literal_parts.append(f"{json.dumps(key)}: END")
                    else:
                        mapping_literal_parts.append(f"{json.dumps(key)}: {json.dumps(value)}")
                mapping_literal = "{%s}" % ", ".join(mapping_literal_parts)
                edge_lines.append(
                    f'builder.add_conditional_edges({json.dumps(source)}, {route_name}, {mapping_literal})'
                )
            else:
                for edge in edges:
                    edge_lines.append(
                        f'builder.add_edge({json.dumps(source)}, {json.dumps(edge["target"])})'
                    )

        start_edges = [
            f"builder.add_edge(START, {json.dumps(root)})" for root in sorted(roots)
        ]

        sink_edges = []
        for sink in sorted(sinks):
            has_outgoing = sink in edge_groups and bool(edge_groups[sink])
            if not has_outgoing:
                sink_edges.append(f"builder.add_edge({json.dumps(sink)}, END)")

        spec_payload = model_dump_compat(spec)
        generated = f'''"""
Auto-generated LangGraph workflow script.
Source workflow: {spec.name} ({spec.version})
Do not edit directly. Regenerate from WorkflowSpec IR.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph


SPEC: Dict[str, Any] = {json.dumps(spec_payload, indent=2, sort_keys=True)}
STEP_CONFIGS: Dict[str, Dict[str, Any]] = {json.dumps(step_configs, indent=2, sort_keys=True)}
STEP_TYPES: Dict[str, str] = {json.dumps(step_types, indent=2, sort_keys=True)}
STEP_TIMEOUTS: Dict[str, int] = {json.dumps(timeout_map, indent=2, sort_keys=True)}
STEP_RETRY: Dict[str, Dict[str, Any]] = {json.dumps(retry_map, indent=2, sort_keys=True)}
OUTPUT_BINDINGS: Dict[str, List[str]] = {json.dumps(output_bindings, indent=2, sort_keys=True)}


class WorkflowState(TypedDict, total=False):
    trace_id: str
    input: Dict[str, Any]
    step_results: Dict[str, Any]
    outputs: Dict[str, Any]
    errors: List[str]


class _SafeFormatMap(dict):
    def __missing__(self, key: str) -> str:
        return "{{" + key + "}}"


def _json_log(event: str, **kwargs: Any) -> None:
    payload = {{
        "event": event,
        "timestamp_ms": int(time.time() * 1000),
        **kwargs,
    }}
    print(json.dumps(payload, sort_keys=True), flush=True)


def _eval_condition(expression: str, state: WorkflowState, last_output: Any) -> bool:
    env: Dict[str, Any] = {{
        "state": state,
        "input": state.get("input", {{}}),
        "step_results": state.get("step_results", {{}}),
        "outputs": state.get("outputs", {{}}),
        "last_output": last_output,
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "all": all,
        "any": any,
    }}
    return bool(eval(expression, {{"__builtins__": {{}}}}, env))


def _run_llm(step_id: str, config: Dict[str, Any], state: WorkflowState) -> Any:
    try:
        from langchain_aws import ChatBedrockConverse
    except ImportError as exc:
        raise ImportError(
            "langchain-aws is required for llm steps. Install dependencies in the sandbox."
        ) from exc

    model = config.get("model", "anthropic.claude-3-5-sonnet-20241022-v2:0")
    temperature = float(config.get("temperature", 0))
    max_tokens = int(config.get("max_output_tokens", 1024))
    region_name = config.get("region_name")
    prompt_template = str(config.get("prompt", "You are an assistant."))
    prompt = prompt_template.format_map(
        _SafeFormatMap(
            {{
                "state": state,
                "input": state.get("input", {{}}),
                "step_results": state.get("step_results", {{}}),
                "outputs": state.get("outputs", {{}}),
            }}
        )
    )

    llm = ChatBedrockConverse(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        region_name=region_name,
    )
    response = llm.invoke(prompt)
    if hasattr(response, "content"):
        return response.content
    return str(response)


def _run_tool(step_id: str, config: Dict[str, Any], state: WorkflowState) -> Any:
    tool_name = config.get("tool_name") or config.get("loader") or "passthrough"
    input_payload = state.get("input", {{}})
    if tool_name in {{"passthrough", "auto_document_loader"}}:
        if isinstance(input_payload, dict) and "text" in input_payload:
            return input_payload["text"]
        return input_payload
    if tool_name == "json_extract":
        path = config.get("path")
        if not path:
            return input_payload
        if isinstance(input_payload, dict):
            return input_payload.get(path)
        return None
    raise RuntimeError(f"Unsupported tool '{{tool_name}}' in step '{{step_id}}'.")


def _run_transform(step_id: str, config: Dict[str, Any], state: WorkflowState) -> Any:
    template = config.get("template")
    if template:
        return str(template).format_map(
            _SafeFormatMap(
                {{
                    "state": state,
                    "input": state.get("input", {{}}),
                    "step_results": state.get("step_results", {{}}),
                    "outputs": state.get("outputs", {{}}),
                }}
            )
        )
    source_step = config.get("source_step")
    if source_step:
        return state.get("step_results", {{}}).get(source_step)
    return state.get("input", {{}})


def _run_condition(step_id: str, config: Dict[str, Any], state: WorkflowState) -> Any:
    expression = config.get("expression") or config.get("condition")
    if not expression:
        return True
    return _eval_condition(str(expression), state, state.get("step_results", {{}}).get(step_id))


def _execute_step(step_id: str, step_type: str, state: WorkflowState) -> Dict[str, Any]:
    config = STEP_CONFIGS.get(step_id, {{}})
    start = time.time()
    _json_log("step_start", trace_id=state.get("trace_id"), step_id=step_id, step_type=step_type)
    try:
        if step_type == "llm":
            result = _run_llm(step_id, config, state)
        elif step_type == "tool":
            result = _run_tool(step_id, config, state)
        elif step_type == "transform":
            result = _run_transform(step_id, config, state)
        elif step_type == "condition":
            result = _run_condition(step_id, config, state)
        else:
            raise RuntimeError(f"Unknown step type '{{step_type}}' for step '{{step_id}}'.")

        step_results = dict(state.get("step_results", {{}}))
        step_results[step_id] = result
        updates: Dict[str, Any] = {{"step_results": step_results}}
        if step_id in OUTPUT_BINDINGS:
            outputs = dict(state.get("outputs", {{}}))
            for output_name in OUTPUT_BINDINGS[step_id]:
                outputs[output_name] = result
            updates["outputs"] = outputs

        _json_log(
            "step_complete",
            trace_id=state.get("trace_id"),
            step_id=step_id,
            latency_ms=int((time.time() - start) * 1000),
        )
        return updates
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"{{type(exc).__name__}}: {{exc}}")
        _json_log("step_error", trace_id=state.get("trace_id"), step_id=step_id, error=str(exc))
        raise RuntimeError(f"Step '{{step_id}}' failed: {{exc}}")


{chr(10).join(node_defs)}
{chr(10).join(routing_defs)}


builder = StateGraph(WorkflowState)
{chr(10).join(add_node_lines)}
{chr(10).join(start_edges)}
{chr(10).join(edge_lines)}
{chr(10).join(sink_edges)}
GRAPH = builder.compile()


def run_workflow(initial_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state: Dict[str, Any] = dict(initial_state or {{}})
    state.setdefault("trace_id", str(uuid.uuid4()))
    state.setdefault("input", {{}})
    state.setdefault("step_results", {{}})
    state.setdefault("outputs", {{}})
    state.setdefault("errors", [])
    return GRAPH.invoke(state)


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    input_state = json.loads(raw) if raw else {{}}
    result = run_workflow(input_state)
    print(json.dumps(result, sort_keys=True, default=str))
'''
        return generated
