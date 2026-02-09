"""
Generated workflow runtime.
Workflow: smoke_todo_flag (1.0.0)
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from tools import TOOL_REGISTRY


WORKFLOW_NAME = "smoke_todo_flag"
WORKFLOW_DESCRIPTION = "Return current time"
SUBTASKS: List[Dict[str, str]] = [
  {
    "description": "Return current time",
    "id": "return_current_time",
    "tool_name": "tool_return_current_time"
  }
]
STEP_DEFS: List[Dict[str, Any]] = [
  {
    "config": {
      "subtask_description": "Return current time",
      "tool_name": "tool_return_current_time"
    },
    "id": "return_current_time",
    "retry_policy": {
      "backoff_strategy": "exponential",
      "initial_delay_seconds": 1.0,
      "max_delay_seconds": 30.0,
      "max_retries": 2
    },
    "timeout_seconds": 120,
    "type": "tool"
  },
  {
    "config": {
      "max_output_tokens": 1024,
      "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
      "prompt": "You are the synthesis head. Combine independent subtask outputs into one clear, direct plain-text answer for the user. Keep the answer coherent with the approved plan and user intent. Avoid JSON output.",
      "temperature": 0
    },
    "id": "synthesize",
    "retry_policy": {
      "backoff_strategy": "exponential",
      "initial_delay_seconds": 1.0,
      "max_delay_seconds": 30.0,
      "max_retries": 2
    },
    "timeout_seconds": 120,
    "type": "llm"
  }
]
EDGE_DEFS: List[Dict[str, Any]] = [
  {
    "condition": null,
    "source": "return_current_time",
    "target": "synthesize"
  }
]
OUTPUT_DEFS: List[Dict[str, Any]] = [
  {
    "data_type": "string",
    "id": "final_answer",
    "name": "final_answer",
    "source_step": "synthesize"
  }
]
DOC_REQUIRED: bool = false
SUPPORTED_DOC_EXTENSIONS: List[str] = [".txt", ".md", ".pdf", ".docx", ".doc"]
SYNTHESIS_PROMPT: str = "You are the synthesis head. Combine independent subtask outputs into one clear, direct plain-text answer for the user. Keep the answer coherent with the approved plan and user intent. Avoid JSON output."
SYNTH_MODEL_ID: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
APPROVED_PLAN: str = "1. Parse requirements and lock the current task description in shared memory.\n2. Split the task into independent subtasks for tool construction.\n3. Build one tool function per subtask via tool-builder agents.\n4. Verify each tool in a venv with execution-based integrity checks.\n5. Iterate tool fixes until verifier passes or fallback tool is selected.\n6. Assemble a LangGraph workflow that runs subtasks and synthesizes results.\n7. Emit workflow folder with workflow.py, tools.py, README.md, and memory snapshot.\n8. Validate generated code and return user run instructions."
INTENT_SUMMARY: str = "Build a general-purpose workflow generator from natural language requirements. User context: Return current time Execution path: 1. Parse requirements and lock the current task description in shared memory. 2. Split the task into independent subtasks for tool construction. 3. Build one tool function per subtask via tool-builder agents. 4. Verify each tool in a venv with execution-based integrity checks. 5. Iterate tool fix..."
CURRENT_TASK_DESCRIPTION: str = "User Requirements:\nReturn current time\n\nApproved Plan:\n1. Parse requirements and lock the current task description in shared memory.\n2. Split the task into independent subtasks for tool construction.\n3. Build one tool function per subtask via tool-builder agents.\n4. Verify each tool in a venv with execution-based integrity checks.\n5. Iterate tool fixes until verifier passes or fallback tool is selected.\n6. Assemble a LangGraph workflow that runs subtasks and synthesizes results.\n7. Emit workflow folder with workflow.py, tools.py, README.md, and memory snapshot.\n8. Validate generated code and return user run instructions.\n\nIntent Summary:\nBuild a general-purpose workflow generator from natural language requirements. User context: Return current time Execution path: 1. Parse requirements and lock the current task description in shared memory. 2. Split the task into independent subtasks for tool construction. 3. Build one tool function per subtask via tool-builder agents. 4. Verify each tool in a venv with execution-based integrity checks. 5. Iterate tool fix...\n"

STEP_MAP: Dict[str, Dict[str, Any]] = {
    str(step.get("id")): step for step in STEP_DEFS if str(step.get("id", "")).strip()
}
STEP_ORDER: List[str] = [str(step.get("id")) for step in STEP_DEFS if str(step.get("id", "")).strip()]
EDGES_BY_SOURCE: Dict[str, List[Dict[str, Any]]] = {}
IN_DEGREE: Dict[str, int] = {step_id: 0 for step_id in STEP_ORDER}
for edge in EDGE_DEFS:
    source = str(edge.get("source", "")).strip()
    target = str(edge.get("target", "")).strip()
    if not source or not target:
        continue
    EDGES_BY_SOURCE.setdefault(source, []).append(
        {"source": source, "target": target, "condition": edge.get("condition")}
    )
    IN_DEGREE[target] = IN_DEGREE.get(target, 0) + 1

ROOT_STEPS: List[str] = [step_id for step_id in STEP_ORDER if IN_DEGREE.get(step_id, 0) == 0]
if not ROOT_STEPS and STEP_ORDER:
    ROOT_STEPS = [STEP_ORDER[0]]
SINK_STEPS: List[str] = [step_id for step_id in STEP_ORDER if not EDGES_BY_SOURCE.get(step_id)]
OUTPUT_SOURCES: List[str] = [
    str(output.get("source_step", "")).strip()
    for output in OUTPUT_DEFS
    if str(output.get("source_step", "")).strip()
]


class WorkflowState(TypedDict, total=False):
    input: Dict[str, Any]
    step_results: Dict[str, Dict[str, Any]]
    final_answer: str


def _read_document(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")
    ext = file_path.suffix.lower()
    if ext in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8")
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if ext == ".docx":
        from docx import Document

        doc = Document(str(file_path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
    if ext == ".doc":
        import shutil
        import subprocess

        textutil_path = shutil.which("textutil")
        if not textutil_path:
            raise ValueError("'.doc' needs macOS textutil or conversion to '.docx'.")
        converted = subprocess.run(
            [textutil_path, "-convert", "txt", "-stdout", str(file_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return converted.stdout.strip()
    raise ValueError(
        f"Unsupported document extension '{ext}'. Supported: {SUPPORTED_DOC_EXTENSIONS}"
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Workflow: {WORKFLOW_NAME}")
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Primary user question/request text.",
    )
    parser.add_argument(
        "--doc",
        type=str,
        default=None,
        help="Path to input document (txt/md/pdf/docx/doc) when needed.",
    )
    parser.add_argument(
        "--input-json",
        type=str,
        default=None,
        help="Inline JSON payload merged into workflow input.",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        default=None,
        help="JSON file merged into workflow input.",
    )
    return parser


def _build_input_payload(args: argparse.Namespace) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if args.input_json:
        parsed = json.loads(args.input_json)
        if isinstance(parsed, dict):
            payload.update(parsed)
    if args.input_file:
        parsed = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            payload.update(parsed)
    if args.query:
        payload["query"] = args.query
    if args.doc:
        payload["doc_path"] = args.doc
        payload["doc"] = _read_document(args.doc)

    if DOC_REQUIRED and not (
        payload.get("doc") or payload.get("document") or payload.get("text")
    ):
        raise ValueError(
            "This workflow requires a document. Use --doc <path> or pass doc/text in JSON."
        )
    return payload


def _sanitize_result(step_id: str, result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        if "tool" not in result:
            result["tool"] = step_id
        if "status" not in result:
            result["status"] = "ok"
        if "result" not in result:
            result["result"] = ""
        return result
    return {
        "tool": step_id,
        "status": "ok",
        "result": str(result),
    }


def _retry_config(step: Dict[str, Any]) -> Dict[str, Any]:
    policy = dict(step.get("retry_policy") or {})
    try:
        max_retries = max(0, int(policy.get("max_retries", 0)))
    except Exception:
        max_retries = 0
    strategy = str(policy.get("backoff_strategy") or "exponential").strip().lower()
    if strategy not in ("fixed", "exponential"):
        strategy = "exponential"
    try:
        initial_delay = float(policy.get("initial_delay_seconds", 1.0))
    except Exception:
        initial_delay = 1.0
    try:
        max_delay = float(policy.get("max_delay_seconds", 30.0))
    except Exception:
        max_delay = 30.0
    return {
        "max_retries": max_retries,
        "backoff_strategy": strategy,
        "initial_delay_seconds": max(0.0, initial_delay),
        "max_delay_seconds": max(0.0, max_delay),
    }


def _compute_backoff_delay(attempt_index: int, retry_cfg: Dict[str, Any]) -> float:
    initial = float(retry_cfg.get("initial_delay_seconds", 1.0))
    max_delay = float(retry_cfg.get("max_delay_seconds", 30.0))
    strategy = str(retry_cfg.get("backoff_strategy", "exponential")).lower()
    if strategy == "fixed":
        delay = initial
    else:
        delay = initial * (2 ** max(0, attempt_index - 1))
    return max(0.0, min(delay, max_delay))


def _run_with_timeout(callback: Callable[[], Dict[str, Any]], timeout_seconds: int) -> Dict[str, Any]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(callback)
        return future.result(timeout=max(1, int(timeout_seconds)))


def _tool_step_once(step: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
    step_id = str(step.get("id", "unknown_step"))
    config = dict(step.get("config") or {})
    tool_name = str(config.get("tool_name") or step_id).strip()
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        return {
            "tool": tool_name,
            "status": "error",
            "result": f"Missing tool '{tool_name}'.",
        }

    tool_input = dict(state.get("input", {}))
    tool_input["step_id"] = step_id
    tool_input["step_type"] = str(step.get("type", "tool"))
    tool_input["step_config"] = config
    tool_input["subtask_id"] = step_id
    tool_input["subtask_description"] = str(config.get("subtask_description") or "")
    tool_input["current_task_description"] = CURRENT_TASK_DESCRIPTION
    tool_input["intent_summary"] = INTENT_SUMMARY
    tool_input["approved_plan"] = APPROVED_PLAN
    tool_input["prior_step_results"] = dict(state.get("step_results", {}))
    return _sanitize_result(tool_name, tool_fn(tool_input))


def _fallback_synthesis(state: WorkflowState) -> str:
    input_payload = dict(state.get("input", {}))
    step_results = dict(state.get("step_results", {}))
    lines: List[str] = []
    if input_payload.get("query"):
        lines.append(f"Request: {input_payload.get('query')}")
    for step_id in STEP_ORDER:
        step = STEP_MAP.get(step_id, {})
        config = dict(step.get("config") or {})
        desc = str(config.get("subtask_description") or step_id)
        result = step_results.get(step_id, {})
        result_text = str(result.get("result", "")).strip()
        lines.append(f"- {desc}: {result_text}")
    summary = "\n".join(line for line in lines if line).strip()
    return summary or "No answer generated."


def _llm_step_once(step: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
    step_id = str(step.get("id", "llm_step"))
    config = dict(step.get("config") or {})
    prompt_template = str(config.get("prompt") or SYNTHESIS_PROMPT)
    model_id = str(config.get("model") or SYNTH_MODEL_ID)
    try:
        temperature = float(config.get("temperature", 0))
    except Exception:
        temperature = 0.0
    fallback = _fallback_synthesis(state)
    try:
        from langchain_aws import ChatBedrockConverse
    except Exception as exc:
        return {
            "tool": step_id,
            "status": "fallback",
            "result": f"{fallback}\n\n[llm unavailable: {exc}]",
        }

    try:
        llm = ChatBedrockConverse(model=model_id, temperature=temperature)
        prompt = (
            prompt_template
            + "\n\nCurrent task:\n" + CURRENT_TASK_DESCRIPTION
            + "\n\nApproved plan:\n" + APPROVED_PLAN
            + "\n\nIntent summary:\n" + INTENT_SUMMARY
            + "\n\nUser input:\n" + json.dumps(state.get("input", {}), sort_keys=True)
            + "\n\nStep outputs:\n" + json.dumps(state.get("step_results", {}), sort_keys=True)
        )
        response = llm.invoke(prompt)
        content = getattr(response, "content", None)
        if isinstance(content, list):
            answer = " ".join(str(chunk) for chunk in content).strip()
        elif content is None:
            answer = str(response).strip()
        else:
            answer = str(content).strip()
        return {
            "tool": step_id,
            "status": "ok",
            "result": answer or fallback,
        }
    except Exception as exc:
        return {
            "tool": step_id,
            "status": "fallback",
            "result": f"{fallback}\n\n[llm invoke failed: {exc}]",
        }


def _execute_step_once(step: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
    step_type = str(step.get("type", "tool")).strip().lower()
    step_id = str(step.get("id", "unknown_step"))
    if step_type == "tool":
        return _tool_step_once(step, state)
    if step_type == "llm":
        return _llm_step_once(step, state)
    return {
        "tool": step_id,
        "status": "ok",
        "result": json.dumps(
            {
                "note": "No-op for unsupported step type in generated runtime.",
                "step_type": step_type,
            },
            sort_keys=True,
        ),
    }


def _execute_step_with_policy(step: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
    step_id = str(step.get("id", "unknown_step"))
    retry_cfg = _retry_config(step)
    max_retries = int(retry_cfg.get("max_retries", 0))
    try:
        timeout_seconds = max(1, int(step.get("timeout_seconds", 120)))
    except Exception:
        timeout_seconds = 120

    last_error = "Step failed."
    for attempt in range(max_retries + 1):
        try:
            result = _run_with_timeout(
                lambda: _execute_step_once(step, state),
                timeout_seconds=timeout_seconds,
            )
            return _sanitize_result(step_id, result)
        except TimeoutError:
            last_error = (
                f"Step '{step_id}' exceeded timeout {timeout_seconds}s "
                f"(attempt {attempt + 1}/{max_retries + 1})."
            )
        except Exception as exc:
            last_error = str(exc)

        if attempt < max_retries:
            delay = _compute_backoff_delay(attempt + 1, retry_cfg)
            if delay > 0:
                time.sleep(delay)

    return {
        "tool": step_id,
        "status": "error",
        "result": last_error,
    }


def _evaluate_condition(condition: Optional[str], source_output: Dict[str, Any]) -> bool:
    if not condition:
        return True
    cond = str(condition).strip().lower()
    status = str(source_output.get("status", "")).strip().lower()
    if cond in ("ok", "success", "status_ok", "status == ok", "status == 'ok'", 'status == "ok"'):
        return status in ("ok", "success")
    if cond in (
        "error",
        "failed",
        "status_error",
        "status != ok",
        "status != 'ok'",
        'status != "ok"',
    ):
        return status not in ("ok", "success")
    # Unknown condition defaults to True to preserve forward progress.
    return True


def _make_step_node(step_id: str) -> Callable[[WorkflowState], Dict[str, Any]]:
    def _node(state: WorkflowState) -> Dict[str, Any]:
        step = STEP_MAP[step_id]
        result = _execute_step_with_policy(step, state)
        step_results = dict(state.get("step_results", {}))
        step_results[step_id] = result
        updates: Dict[str, Any] = {"step_results": step_results}
        if step_id in OUTPUT_SOURCES:
            updates["final_answer"] = str(result.get("result", "")).strip()
        return updates

    return _node


def _make_router(source_step: str) -> Callable[[WorkflowState], str]:
    def _router(state: WorkflowState) -> str:
        source_output = dict(state.get("step_results", {})).get(source_step, {})
        for edge in EDGES_BY_SOURCE.get(source_step, []):
            target = str(edge.get("target", "")).strip()
            if not target:
                continue
            if _evaluate_condition(edge.get("condition"), source_output):
                return target
        return "__END__"

    return _router


builder = StateGraph(WorkflowState)
for step_id in STEP_ORDER:
    builder.add_node(step_id, _make_step_node(step_id))

for root_step in ROOT_STEPS:
    builder.add_edge(START, root_step)

for source_step in STEP_ORDER:
    outgoing = EDGES_BY_SOURCE.get(source_step, [])
    if not outgoing:
        continue
    has_conditions = any(str(edge.get("condition") or "").strip() for edge in outgoing)
    if not has_conditions:
        for edge in outgoing:
            builder.add_edge(source_step, edge["target"])
        continue
    route_map = {edge["target"]: edge["target"] for edge in outgoing}
    route_map["__END__"] = END
    builder.add_conditional_edges(source_step, _make_router(source_step), route_map)

for sink_step in SINK_STEPS:
    builder.add_edge(sink_step, END)

GRAPH = builder.compile()


def run_workflow(input_payload: Optional[Dict[str, Any]] = None) -> str:
    state: WorkflowState = {
        "input": dict(input_payload or {}),
        "step_results": {},
        "final_answer": "",
    }
    result = GRAPH.invoke(state)
    final_answer = str(result.get("final_answer", "")).strip()
    if final_answer:
        return final_answer
    step_results = dict(result.get("step_results", {}))
    for source_step in OUTPUT_SOURCES:
        row = step_results.get(source_step, {})
        text = str(row.get("result", "")).strip()
        if text:
            return text
    return _fallback_synthesis(result)


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()
    payload = _build_input_payload(args)
    answer = run_workflow(payload)
    print(answer if answer else "No answer generated.")
