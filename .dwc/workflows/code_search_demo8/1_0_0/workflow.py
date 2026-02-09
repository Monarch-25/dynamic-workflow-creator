"""
Generated workflow runtime.
Workflow: code_search_demo8 (1.0.0)
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from tools import TOOL_REGISTRY


WORKFLOW_NAME = "code_search_demo8"
WORKFLOW_DESCRIPTION = "Search python source code with ripgrep for class definitions"
SUBTASKS: List[Dict[str, str]] = [
  {
    "description": "Search python source code with ripgrep for class definitions",
    "id": "task_1",
    "tool_name": "tool_task_1"
  }
]
DOC_REQUIRED: bool = false
SUPPORTED_DOC_EXTENSIONS: List[str] = [".txt", ".md", ".pdf", ".docx", ".doc"]
SYNTHESIS_PROMPT: str = "You are the synthesis head. Combine independent subtask outputs into one clear, direct plain-text answer for the user. Keep the answer coherent with the approved plan and user intent. Avoid JSON output."
SYNTH_MODEL_ID: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
APPROVED_PLAN: str = "1. Parse requirements and lock the current task description in shared memory.\n2. Split the task into independent subtasks for tool construction.\n3. Build one tool function per subtask via tool-builder agents.\n4. Verify each tool in a venv with execution-based integrity checks.\n5. Iterate tool fixes until verifier passes or fallback tool is selected.\n6. Assemble a LangGraph workflow that runs subtasks and synthesizes results.\n7. Emit workflow folder with workflow.py, tools.py, README.md, and memory snapshot.\n8. Validate generated code and return user run instructions."
INTENT_SUMMARY: str = "Build a general-purpose workflow generator from natural language requirements. User context: Search python source code with ripgrep for class definitions Execution path: 1. Parse requirements and lock the current task description in shared memory. 2. Split the task into independent subtasks for tool construction. 3. Build one tool function per subtask via tool-builder agents. 4. Verify each tool in a venv with execution-based integrity checks. 5. Iterate tool fix..."
CURRENT_TASK_DESCRIPTION: str = "User Requirements:\nSearch python source code with ripgrep for class definitions\n\nApproved Plan:\n1. Parse requirements and lock the current task description in shared memory.\n2. Split the task into independent subtasks for tool construction.\n3. Build one tool function per subtask via tool-builder agents.\n4. Verify each tool in a venv with execution-based integrity checks.\n5. Iterate tool fixes until verifier passes or fallback tool is selected.\n6. Assemble a LangGraph workflow that runs subtasks and synthesizes results.\n7. Emit workflow folder with workflow.py, tools.py, README.md, and memory snapshot.\n8. Validate generated code and return user run instructions.\n\nIntent Summary:\nBuild a general-purpose workflow generator from natural language requirements. User context: Search python source code with ripgrep for class definitions Execution path: 1. Parse requirements and lock the current task description in shared memory. 2. Split the task into independent subtasks for tool construction. 3. Build one tool function per subtask via tool-builder agents. 4. Verify each tool in a venv with execution-based integrity checks. 5. Iterate tool fix...\n"


class WorkflowState(TypedDict, total=False):
    input: Dict[str, Any]
    subtask_results: Dict[str, Dict[str, Any]]
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


def _run_single_subtask(subtask: Dict[str, str], base_input: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = subtask["tool_name"]
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        return {
            "tool": tool_name,
            "status": "error",
            "result": f"Missing tool '{tool_name}'.",
        }

    tool_input = dict(base_input)
    tool_input["subtask_id"] = subtask["id"]
    tool_input["subtask_description"] = subtask["description"]
    tool_input["current_task_description"] = CURRENT_TASK_DESCRIPTION
    tool_input["intent_summary"] = INTENT_SUMMARY

    result = tool_fn(tool_input)
    if isinstance(result, dict):
        return result
    return {
        "tool": tool_name,
        "status": "ok",
        "result": str(result),
    }


def run_subtasks_node(state: WorkflowState) -> Dict[str, Any]:
    base_input = dict(state.get("input", {}))
    outputs: Dict[str, Dict[str, Any]] = {}
    max_workers = max(1, min(4, len(SUBTASKS)))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_run_single_subtask, subtask, base_input): subtask
            for subtask in SUBTASKS
        }
        for future in as_completed(futures):
            subtask = futures[future]
            subtask_id = subtask["id"]
            try:
                outputs[subtask_id] = future.result(timeout=60)
            except Exception as exc:
                outputs[subtask_id] = {
                    "tool": subtask["tool_name"],
                    "status": "error",
                    "result": str(exc),
                }
    return {"subtask_results": outputs}


def _fallback_synthesis(input_payload: Dict[str, Any], subtask_results: Dict[str, Any]) -> str:
    lines: List[str] = []
    if input_payload.get("query"):
        lines.append(f"Request: {input_payload.get('query')}")
    for subtask in SUBTASKS:
        result = subtask_results.get(subtask["id"], {})
        result_text = str(result.get("result", "")).strip()
        lines.append(f"- {subtask['description']}: {result_text}")
    summary = "\n".join(line for line in lines if line).strip()
    return summary or "No answer generated."


def synthesize_node(state: WorkflowState) -> Dict[str, Any]:
    input_payload = dict(state.get("input", {}))
    subtask_results = dict(state.get("subtask_results", {}))
    fallback = _fallback_synthesis(input_payload, subtask_results)

    try:
        from langchain_aws import ChatBedrockConverse
    except Exception:
        return {"final_answer": fallback}

    try:
        llm = ChatBedrockConverse(model=SYNTH_MODEL_ID, temperature=0)
        prompt = (
            SYNTHESIS_PROMPT
            + "\n\nCurrent task:\n" + CURRENT_TASK_DESCRIPTION
            + "\n\nApproved plan:\n" + APPROVED_PLAN
            + "\n\nIntent summary:\n" + INTENT_SUMMARY
            + "\n\nUser input:\n" + json.dumps(input_payload, sort_keys=True)
            + "\n\nSubtask outputs:\n" + json.dumps(subtask_results, sort_keys=True)
        )
        response = llm.invoke(prompt)
        content = getattr(response, "content", None)
        if isinstance(content, list):
            answer = " ".join(str(chunk) for chunk in content).strip()
        elif content is None:
            answer = str(response).strip()
        else:
            answer = str(content).strip()
        return {"final_answer": answer or fallback}
    except Exception:
        return {"final_answer": fallback}


builder = StateGraph(WorkflowState)
builder.add_node("run_subtasks", run_subtasks_node)
builder.add_node("synthesize", synthesize_node)
builder.add_edge(START, "run_subtasks")
builder.add_edge("run_subtasks", "synthesize")
builder.add_edge("synthesize", END)
GRAPH = builder.compile()


def run_workflow(input_payload: Optional[Dict[str, Any]] = None) -> str:
    state: WorkflowState = {
        "input": dict(input_payload or {}),
        "subtask_results": {},
        "final_answer": "",
    }
    result = GRAPH.invoke(state)
    return str(result.get("final_answer", "")).strip()


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()
    payload = _build_input_payload(args)
    answer = run_workflow(payload)
    print(answer if answer else "No answer generated.")
