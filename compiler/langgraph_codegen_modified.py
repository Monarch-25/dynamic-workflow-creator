"""
LangGraph code generation from optimized WorkflowSpec.
"""

from __future__ import annotations

import json
import pprint
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dwc.ir.spec_schema import WorkflowSpec
from dwc.llm import DWC_BEDROCK_MODEL_ID


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_") or "workflow"


def _safe_identifier(value: str) -> str:
    candidate = _safe_name(value).lower()
    if candidate and candidate[0].isdigit():
        candidate = f"tool_{candidate}"
    return candidate


def _json_to_python_literal(json_str: str) -> str:
    """Convert JSON text into a valid Python literal string.

    This round-trips through ``json.loads`` so JSON tokens (null/true/false)
    become Python literals (None/True/False) without touching normal strings.
    """
    parsed = json.loads(json_str)
    return pprint.pformat(parsed, width=100, sort_dicts=False)


class WorkflowIOContract(BaseModel):
    requires_document: bool = False
    required_fields: List[str] = Field(default_factory=list)
    optional_fields: List[str] = Field(default_factory=list)
    supported_doc_extensions: List[str] = Field(
        default_factory=lambda: [".txt", ".md", ".pdf", ".docx", ".doc"]
    )


class CodegenResult(BaseModel):
    script_path: str
    workflow_dir: str
    runbook_path: str
    spec_path: str
    tools_path: str
    requirements: List[str] = Field(default_factory=list)
    entrypoint: str = "run_workflow"
    io_contract: WorkflowIOContract = Field(default_factory=WorkflowIOContract)


class LangGraphCodeGenerator:
    def __init__(self, output_dir: str = ".dwc/workflows") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self, spec: WorkflowSpec, filename: Optional[str] = None
    ) -> CodegenResult:
        safe_name = _safe_name(spec.name)
        safe_version = _safe_name(spec.version)
        workflow_dir = self.output_dir / safe_name / safe_version
        workflow_dir.mkdir(parents=True, exist_ok=True)

        script_filename = filename or "workflow.py"
        script_path = workflow_dir / script_filename
        tools_path = workflow_dir / "tools.py"
        spec_path = workflow_dir / "spec.json"
        runbook_path = workflow_dir / "README.md"

        io_contract = self._build_io_contract(spec)
        subtasks = self._extract_subtasks(spec)
        tool_functions = self._extract_tool_functions(spec, subtasks)
        synthesis_prompt = str(
            spec.metadata.get(
                "synthesis_prompt",
                (
                    "You are the synthesis head. Combine subtask outputs into one "
                    "coherent plain-text answer. Do not return JSON."
                ),
            )
        )
        approved_plan = str(spec.metadata.get("approved_plan", ""))
        intent_summary = str(spec.metadata.get("intent_summary", ""))
        current_task_description = str(
            spec.metadata.get("current_task_description", spec.description)
        )

        spec_path.write_text(spec.to_json(indent=2), encoding="utf-8")
        tools_path.write_text(
            self.render_tools_module(tool_functions), encoding="utf-8"
        )
        script_path.write_text(
            self.render_workflow_script(
                spec=spec,
                subtasks=subtasks,
                io_contract=io_contract,
                synthesis_prompt=synthesis_prompt,
                approved_plan=approved_plan,
                intent_summary=intent_summary,
                current_task_description=current_task_description,
            ),
            encoding="utf-8",
        )
        runbook_path.write_text(
            self.render_runbook(
                spec=spec,
                subtasks=subtasks,
                io_contract=io_contract,
                script_filename=script_filename,
            ),
            encoding="utf-8",
        )

        requirements = [
            "langgraph>=0.2.0",
            "langchain-aws>=0.2.0",
            "boto3>=1.34.0",
        ]
        if io_contract.requires_document:
            requirements.extend(["pypdf>=4.0.0", "python-docx>=1.1.0"])

        return CodegenResult(
            script_path=str(script_path),
            workflow_dir=str(workflow_dir),
            runbook_path=str(runbook_path),
            spec_path=str(spec_path),
            tools_path=str(tools_path),
            requirements=sorted(set(requirements)),
            entrypoint="run_workflow",
            io_contract=io_contract,
        )

    def _build_io_contract(self, spec: WorkflowSpec) -> WorkflowIOContract:
        required_fields: List[str] = []
        optional_fields: List[str] = []
        requires_document = False

        for input_spec in spec.inputs:
            field_name = input_spec.name or input_spec.id
            if input_spec.required:
                required_fields.append(field_name)
            else:
                optional_fields.append(field_name)

            signature = " ".join(
                [
                    input_spec.id,
                    input_spec.name,
                    input_spec.data_type,
                    input_spec.description or "",
                ]
            ).lower()
            if any(
                token in signature
                for token in ("doc", "document", "pdf", "docx", "file")
            ):
                requires_document = True

        for subtask in self._extract_subtasks(spec):
            if any(
                token in subtask["description"].lower()
                for token in ("doc", "document", "pdf", "docx", "file")
            ):
                requires_document = True

        return WorkflowIOContract(
            requires_document=requires_document,
            required_fields=sorted(set(required_fields)),
            optional_fields=sorted(set(optional_fields)),
        )

    def _extract_subtasks(self, spec: WorkflowSpec) -> List[Dict[str, str]]:
        rows = spec.metadata.get("subtasks", [])
        subtasks: List[Dict[str, str]] = []
        if isinstance(rows, list):
            for idx, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    continue
                subtask_id = str(row.get("id", f"task_{idx}")).strip() or f"task_{idx}"
                desc = str(row.get("description", "")).strip()
                tool_name = str(
                    row.get("tool_name", f"tool_{_safe_identifier(subtask_id)}")
                ).strip() or f"tool_{_safe_identifier(subtask_id)}"
                if not desc:
                    continue
                subtasks.append(
                    {"id": subtask_id, "description": desc, "tool_name": tool_name}
                )

        if subtasks:
            return subtasks

        # Fallback from tool steps.
        for idx, step in enumerate(spec.steps, start=1):
            if step.type != "tool":
                continue
            desc = str(
                step.config.get("subtask_description")
                or step.config.get("description")
                or step.id
            )
            tool_name = str(step.config.get("tool_name") or f"tool_{_safe_identifier(step.id)}")
            subtasks.append(
                {"id": step.id or f"task_{idx}", "description": desc, "tool_name": tool_name}
            )

        if not subtasks:
            subtasks = [
                {
                    "id": "task_1",
                    "description": "Handle the workflow request.",
                    "tool_name": "tool_task_1",
                }
            ]
        return subtasks

    def _extract_tool_functions(
        self, spec: WorkflowSpec, subtasks: List[Dict[str, str]]
    ) -> Dict[str, Dict[str, str]]:
        raw = spec.metadata.get("tool_functions", {})
        tool_functions: Dict[str, Dict[str, str]] = {}

        if isinstance(raw, dict):
            for name, payload in raw.items():
                if not isinstance(payload, dict):
                    continue
                code = str(payload.get("code", "")).strip()
                description = str(payload.get("description", "")).strip()
                if code:
                    tool_functions[str(name)] = {
                        "description": description or str(name),
                        "code": code + ("\n" if not code.endswith("\n") else ""),
                    }

        for subtask in subtasks:
            tool_name = subtask["tool_name"]
            if tool_name not in tool_functions:
                tool_functions[tool_name] = {
                    "description": subtask["description"],
                    "code": self._default_tool_code(
                        function_name=tool_name, description=subtask["description"]
                    ),
                }
        return tool_functions

    @staticmethod
    def _default_tool_code(function_name: str, description: str) -> str:
        return f"""from typing import Any, Dict

def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = task_input.get("query") or task_input.get("doc") or task_input.get("text") or ""
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": f"{description}: {{value}}",
    }}
"""

    def render_tools_module(self, tool_functions: Dict[str, Dict[str, str]]) -> str:
        blocks: List[str] = [
            '"""Generated tool arsenal for workflow."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Any, Callable, Dict, Optional, Tuple",
            "",
            "import os",
            "import shlex",
            "import subprocess",
            "import sys",
            "",
            "BANNED_CLI_PATTERNS = (",
            '    "rm ",',
            '    "rm -",',
            '    "shutil.rmtree",',
            '    "os.remove",',
            '    "mkfs",',
            '    "shutdown",',
            '    "reboot",',
            ")",
            "",
            "BLOCKED_SHELL_TOKENS = (",
            '    "|",',
            '    "&&",',
            '    "||",',
            '    ";",',
            '    ">",',
            '    "<",',
            '    "$(",',
            '    "`",',
            ")",
            "",
            "def _contains_blocked_tokens(command: str) -> bool:",
            "    return any(token in command for token in BLOCKED_SHELL_TOKENS)",
            "",
            "def _decision_from_user_message(user_message: str, command: str) -> Tuple[str, Optional[str]]:",
            "    message = user_message.strip()",
            "    lowered = message.lower()",
            '    if lowered.startswith("modify:"):',
            '        replacement = message.split(":", 1)[1].strip()',
            "        if replacement:",
            '            return "execute", replacement',
            '    if lowered.startswith("replace with "):',
            "        replacement = message[len('replace with '):].strip()",
            "        if replacement:",
            '            return "execute", replacement',
            "    if any(token in lowered for token in (",
            '        "execute", "run", "yes", "approve", "proceed", "continue"',
            "    )):",
            '        return "execute", command',
            "    if any(token in lowered for token in (",
            '        "skip", "no", "deny", "block", "cancel", "stop", "other", "something else"',
            "    )):",
            '        return "skip", None',
            '    return "skip", None',
            "",
            "def _prompt_shell_decision(command: str) -> Tuple[str, Optional[str]]:",
            '    print("[safe_cli] Pending shell command:")',
            '    print(f"[safe_cli]   {command}")',
            '    print("[safe_cli] Reply: execute | modify:<new command> | skip")',
            '    user_message = input("[safe_cli] > ").strip()',
            "    return _decision_from_user_message(user_message, command)",
            "",
            "def _resolve_shell_command(command: str, user_message: Optional[str] = None) -> Optional[str]:",
            '    mode = os.getenv("DWC_SAFE_CLI_MODE", "prompt").strip().lower()',
            '    if mode == "allow":',
            "        return command",
            '    if mode == "deny":',
            "        return None",
            '    seed_message = (user_message or "").strip()',
            "    if not seed_message:",
            '        seed_message = os.getenv("DWC_SAFE_CLI_USER_MESSAGE", "").strip()',
            "    if seed_message:",
            "        action, final_command = _decision_from_user_message(seed_message, command)",
            '        if action == "execute" and final_command:',
            "            return final_command",
            "        return None",
            "    if not sys.stdin.isatty():",
            '        raise RuntimeError(',
            '            "safe_cli requires interactive approval. Set DWC_SAFE_CLI_MODE=allow|deny or DWC_SAFE_CLI_USER_MESSAGE."',
            "        )",
            "    action, final_command = _prompt_shell_decision(command)",
            '    if action == "execute" and final_command:',
            "        return final_command",
            "    return None",
            "",
            "def safe_cli(command: str, user_message: Optional[str] = None) -> str:",
            "    approved_command = _resolve_shell_command(command, user_message=user_message)",
            "    if not approved_command:",
            '        return "Command skipped by user approval policy."',
            "    lower = approved_command.lower()",
            "    if any(pattern in lower for pattern in BANNED_CLI_PATTERNS):",
            '        raise ValueError("Blocked potentially harmful CLI command.")',
            "    if _contains_blocked_tokens(approved_command):",
            '        raise ValueError("Blocked shell meta-operators. Provide a direct argv-style command.")',
            "    try:",
            "        argv = shlex.split(approved_command)",
            "    except ValueError as exc:",
            '        raise ValueError(f"Unable to parse command: {exc}") from exc',
            "    if not argv:",
            '        raise ValueError("Empty CLI command after parsing.")',
            "    result = subprocess.run(",
            "        argv, check=True, capture_output=True, text=True",
            "    )",
            "    return result.stdout.strip()",
            "",
        ]

        registry_entries: List[str] = []
        for tool_name, payload in tool_functions.items():
            code = str(payload.get("code", "")).rstrip() + "\n"
            blocks.append(code)
            blocks.append("")
            registry_entries.append(f'    "{tool_name}": {tool_name},')

        blocks.append("TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {")
        blocks.extend(registry_entries)
        blocks.append("}")
        blocks.append("")
        return "\n".join(blocks)

    def render_workflow_script(
        self,
        *,
        spec: WorkflowSpec,
        subtasks: List[Dict[str, str]],
        io_contract: WorkflowIOContract,
        synthesis_prompt: str,
        approved_plan: str,
        intent_summary: str,
        current_task_description: str,
    ) -> str:
        payload_steps = _json_to_python_literal(json.dumps(
            [
                {
                    "id": step.id,
                    "type": step.type,
                    "config": dict(step.config),
                    "timeout_seconds": int(step.timeout_seconds),
                    "retry_policy": {
                        "max_retries": int(step.retry_policy.max_retries),
                        "backoff_strategy": str(step.retry_policy.backoff_strategy),
                        "initial_delay_seconds": float(step.retry_policy.initial_delay_seconds),
                        "max_delay_seconds": float(step.retry_policy.max_delay_seconds),
                    },
                }
                for step in spec.steps
            ],
            indent=2,
            sort_keys=True,
        ))
        payload_edges = _json_to_python_literal(json.dumps(
            [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "condition": edge.condition,
                }
                for edge in spec.edges
            ],
            indent=2,
            sort_keys=True,
        ))
        payload_outputs = _json_to_python_literal(json.dumps(
            [
                {
                    "id": output.id,
                    "name": output.name,
                    "source_step": output.source_step,
                    "data_type": output.data_type,
                }
                for output in spec.outputs
            ],
            indent=2,
            sort_keys=True,
        ))
        payload_subtasks = _json_to_python_literal(
            json.dumps(subtasks, indent=2, sort_keys=True)
        )
        payload_extensions = _json_to_python_literal(
            json.dumps(io_contract.supported_doc_extensions, sort_keys=True)
        )
        payload_prompt = _json_to_python_literal(json.dumps(synthesis_prompt))
        payload_plan = _json_to_python_literal(json.dumps(approved_plan))
        payload_intent = _json_to_python_literal(json.dumps(intent_summary))
        payload_task = _json_to_python_literal(json.dumps(current_task_description))
        payload_model = _json_to_python_literal(json.dumps(DWC_BEDROCK_MODEL_ID))
        payload_doc_required = "True" if io_contract.requires_document else "False"

        return f'''"""
Generated workflow runtime.
Workflow: {spec.name} ({spec.version})
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from tools import TOOL_REGISTRY


WORKFLOW_NAME = {json.dumps(spec.name)}
WORKFLOW_DESCRIPTION = {json.dumps(spec.description)}
SUBTASKS: List[Dict[str, str]] = {payload_subtasks}
STEP_DEFS: List[Dict[str, Any]] = {payload_steps}
EDGE_DEFS: List[Dict[str, Any]] = {payload_edges}
OUTPUT_DEFS: List[Dict[str, Any]] = {payload_outputs}
DOC_REQUIRED: bool = {payload_doc_required}
SUPPORTED_DOC_EXTENSIONS: List[str] = {payload_extensions}
SYNTHESIS_PROMPT: str = {payload_prompt}
SYNTH_MODEL_ID: str = {payload_model}
APPROVED_PLAN: str = {payload_plan}
INTENT_SUMMARY: str = {payload_intent}
CURRENT_TASK_DESCRIPTION: str = {payload_task}

STEP_MAP: Dict[str, Dict[str, Any]] = {{
    str(step.get("id")): step for step in STEP_DEFS if str(step.get("id", "")).strip()
}}
STEP_ORDER: List[str] = [str(step.get("id")) for step in STEP_DEFS if str(step.get("id", "")).strip()]
EDGES_BY_SOURCE: Dict[str, List[Dict[str, Any]]] = {{}}
IN_DEGREE: Dict[str, int] = {{step_id: 0 for step_id in STEP_ORDER}}
for edge in EDGE_DEFS:
    source = str(edge.get("source", "")).strip()
    target = str(edge.get("target", "")).strip()
    if not source or not target:
        continue
    EDGES_BY_SOURCE.setdefault(source, []).append(
        {{"source": source, "target": target, "condition": edge.get("condition")}}
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


def _merge_step_results(left: Dict[str, Dict[str, Any]], right: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Merge step results from concurrent nodes."""
    merged = dict(left) if left else {{}}
    if right:
        merged.update(right)
    return merged


class WorkflowState(TypedDict, total=False):
    input: Dict[str, Any]
    step_results: Annotated[Dict[str, Dict[str, Any]], _merge_step_results]
    final_answer: str


def _read_document(path: str) -> str:
    file_path = Path(path).expanduser()
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()
    else:
        file_path = file_path.resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Document not found: {{file_path}}")
    ext = file_path.suffix.lower()
    if ext in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8")
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return "\\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if ext == ".docx":
        from docx import Document

        doc = Document(str(file_path))
        return "\\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
    if ext == ".doc":
        import shutil
        import subprocess

        candidates: List[List[str]] = []
        if shutil.which("antiword"):
            candidates.append(["antiword", str(file_path)])
        if shutil.which("catdoc"):
            candidates.append(["catdoc", str(file_path)])
        textutil_path = shutil.which("textutil")
        if textutil_path:
            candidates.append([textutil_path, "-convert", "txt", "-stdout", str(file_path)])

        errors: List[str] = []
        for command in candidates:
            try:
                converted = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                output = converted.stdout.strip()
                if output:
                    return output
                errors.append(f"{{command[0]}} returned empty output")
            except subprocess.CalledProcessError as exc:
                snippet = (exc.stderr or exc.stdout or "").strip().replace("\\n", " ")
                errors.append(f"{{command[0]}} failed: {{snippet[:120]}}")

        detail = "; ".join(errors) if errors else "no compatible converter found in PATH"
        raise ValueError(
            "Cannot parse '.doc' file. Install antiword/catdoc (Linux) or use macOS textutil, "
            "or convert the file to '.docx'. Details: " + detail
        )
    raise ValueError(
        f"Unsupported document extension '{{ext}}'. Supported: {{SUPPORTED_DOC_EXTENSIONS}}"
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Workflow: {{WORKFLOW_NAME}}")
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
    payload: Dict[str, Any] = {{}}
    if args.input_json:
        parsed = json.loads(args.input_json)
        if isinstance(parsed, dict):
            payload.update(parsed)
    if args.input_file:
        input_file_path = Path(args.input_file).expanduser()
        if not input_file_path.is_absolute():
            input_file_path = (Path.cwd() / input_file_path).resolve()
        else:
            input_file_path = input_file_path.resolve()
        parsed = json.loads(input_file_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            payload.update(parsed)
    if args.query:
        payload["query"] = args.query
    if args.doc:
        doc_path = Path(args.doc).expanduser()
        if not doc_path.is_absolute():
            doc_path = (Path.cwd() / doc_path).resolve()
        else:
            doc_path = doc_path.resolve()
        payload["doc_path"] = str(doc_path)
        payload["doc"] = _read_document(str(doc_path))

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
    return {{
        "tool": step_id,
        "status": "ok",
        "result": str(result),
    }}


def _retry_config(step: Dict[str, Any]) -> Dict[str, Any]:
    policy = dict(step.get("retry_policy") or {{}})
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
    return {{
        "max_retries": max_retries,
        "backoff_strategy": strategy,
        "initial_delay_seconds": max(0.0, initial_delay),
        "max_delay_seconds": max(0.0, max_delay),
    }}


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
    config = dict(step.get("config") or {{}})
    tool_name = str(config.get("tool_name") or step_id).strip()
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        return {{
            "tool": tool_name,
            "status": "error",
            "result": f"Missing tool '{{tool_name}}'.",
        }}

    tool_input = dict(state.get("input", {{}}))
    tool_input["step_id"] = step_id
    tool_input["step_type"] = str(step.get("type", "tool"))
    tool_input["step_config"] = config
    tool_input["subtask_id"] = step_id
    tool_input["subtask_description"] = str(config.get("subtask_description") or "")
    tool_input["current_task_description"] = CURRENT_TASK_DESCRIPTION
    tool_input["intent_summary"] = INTENT_SUMMARY
    tool_input["approved_plan"] = APPROVED_PLAN
    tool_input["prior_step_results"] = dict(state.get("step_results", {{}}))
    return _sanitize_result(tool_name, tool_fn(tool_input))


def _fallback_synthesis(state: WorkflowState) -> str:
    input_payload = dict(state.get("input", {{}}))
    step_results = dict(state.get("step_results", {{}}))
    lines: List[str] = []
    if input_payload.get("query"):
        lines.append(f"Request: {{input_payload.get('query')}}")
    for step_id in STEP_ORDER:
        step = STEP_MAP.get(step_id, {{}})
        config = dict(step.get("config") or {{}})
        desc = str(config.get("subtask_description") or step_id)
        result = step_results.get(step_id, {{}})
        result_text = str(result.get("result", "")).strip()
        lines.append(f"- {{desc}}: {{result_text}}")
    summary = "\\n".join(line for line in lines if line).strip()
    return summary or "No answer generated."


def _llm_step_once(step: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
    step_id = str(step.get("id", "llm_step"))
    config = dict(step.get("config") or {{}})
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
        return {{
            "tool": step_id,
            "status": "fallback",
            "result": f"{{fallback}}\\n\\n[llm unavailable: {{exc}}]",
        }}

    try:
        llm = ChatBedrockConverse(model=model_id, temperature=temperature)
        prompt = (
            prompt_template
            + "\\n\\nCurrent task:\\n" + CURRENT_TASK_DESCRIPTION
            + "\\n\\nApproved plan:\\n" + APPROVED_PLAN
            + "\\n\\nIntent summary:\\n" + INTENT_SUMMARY
            + "\\n\\nUser input:\\n" + json.dumps(state.get("input", {{}}), sort_keys=True)
            + "\\n\\nStep outputs:\\n" + json.dumps(state.get("step_results", {{}}), sort_keys=True)
        )
        response = llm.invoke(prompt)
        content = getattr(response, "content", None)
        if isinstance(content, list):
            answer = " ".join(str(chunk) for chunk in content).strip()
        elif content is None:
            answer = str(response).strip()
        else:
            answer = str(content).strip()
        return {{
            "tool": step_id,
            "status": "ok",
            "result": answer or fallback,
        }}
    except Exception as exc:
        return {{
            "tool": step_id,
            "status": "fallback",
            "result": f"{{fallback}}\\n\\n[llm invoke failed: {{exc}}]",
        }}


def _execute_step_once(step: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
    step_type = str(step.get("type", "tool")).strip().lower()
    step_id = str(step.get("id", "unknown_step"))
    if step_type == "tool":
        return _tool_step_once(step, state)
    if step_type == "llm":
        return _llm_step_once(step, state)
    return {{
        "tool": step_id,
        "status": "ok",
        "result": json.dumps(
            {{
                "note": "No-op for unsupported step type in generated runtime.",
                "step_type": step_type,
            }},
            sort_keys=True,
        ),
    }}


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
                f"Step '{{step_id}}' exceeded timeout {{timeout_seconds}}s "
                f"(attempt {{attempt + 1}}/{{max_retries + 1}})."
            )
        except Exception as exc:
            last_error = str(exc)

        if attempt < max_retries:
            delay = _compute_backoff_delay(attempt + 1, retry_cfg)
            if delay > 0:
                time.sleep(delay)

    return {{
        "tool": step_id,
        "status": "error",
        "result": last_error,
    }}


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
        step_results = dict(state.get("step_results", {{}}))
        step_results[step_id] = result
        updates: Dict[str, Any] = {{"step_results": step_results}}
        if step_id in OUTPUT_SOURCES:
            updates["final_answer"] = str(result.get("result", "")).strip()
        return updates

    return _node


def _make_router(source_step: str) -> Callable[[WorkflowState], str]:
    def _router(state: WorkflowState) -> str:
        source_output = dict(state.get("step_results", {{}})).get(source_step, {{}})
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
    route_map = {{edge["target"]: edge["target"] for edge in outgoing}}
    route_map["__END__"] = END
    builder.add_conditional_edges(source_step, _make_router(source_step), route_map)

for sink_step in SINK_STEPS:
    builder.add_edge(sink_step, END)

GRAPH = builder.compile()


def run_workflow(input_payload: Optional[Dict[str, Any]] = None) -> str:
    state: WorkflowState = {{
        "input": dict(input_payload or {{}}),
        "step_results": {{}},
        "final_answer": "",
    }}
    result = GRAPH.invoke(state)
    final_answer = str(result.get("final_answer", "")).strip()
    if final_answer:
        return final_answer
    step_results = dict(result.get("step_results", {{}}))
    for source_step in OUTPUT_SOURCES:
        row = step_results.get(source_step, {{}})
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
'''

    def render_runbook(
        self,
        *,
        spec: WorkflowSpec,
        subtasks: List[Dict[str, str]],
        io_contract: WorkflowIOContract,
        script_filename: str,
    ) -> str:
        required_fields = ", ".join(io_contract.required_fields) or "none"
        optional_fields = ", ".join(io_contract.optional_fields) or "none"
        subtask_lines = "\n".join(
            f"- `{subtask['id']}`: {subtask['description']} (tool: `{subtask['tool_name']}`)"
            for subtask in subtasks
        )
        doc_required_text = (
            "Yes (`--doc /path/to/file` required unless doc/text passed via JSON)."
            if io_contract.requires_document
            else "No."
        )
        return f"""# {spec.name} ({spec.version})

## Capability
{spec.description}

## Subtasks
{subtask_lines}

## Runtime Requirements
- Document required: {doc_required_text}
- Required input fields: {required_fields}
- Optional input fields: {optional_fields}
- Supported document extensions: {", ".join(io_contract.supported_doc_extensions)}

## Run
Default:
```bash
python {script_filename}
```

With query:
```bash
python {script_filename} --query "Your question here"
```

With document:
```bash
python {script_filename} --doc ./input.txt
```

## Output
- The script prints plain-text final answer to terminal.
- No JSON is emitted by default.

## Notes
- `tools.py` contains verifier-approved tool functions.
- `spec.json` stores the compiled workflow spec.
- `memory/` snapshot mirrors shared task + working memories used during build.
- Any tool that calls `safe_cli` requires command approval (`execute` / `modify:<cmd>` / `skip`).
- Non-interactive control: `DWC_SAFE_CLI_MODE=allow|deny|prompt` and optional `DWC_SAFE_CLI_USER_MESSAGE`.
"""
