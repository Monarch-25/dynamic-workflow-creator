"""
Tool creation agent for generating callable subtask functions.
"""

from __future__ import annotations

import json
import logging
import re
from textwrap import dedent
from typing import Any, Optional

from pydantic import BaseModel

from dwc.agents.langchain_tool_calling import invoke_bound_schema
from dwc.agents.spec_generator import LLMProtocol
from dwc.agents.subtask_agent import SubtaskSpec
from dwc.agents.tool_catalog import BuiltinToolCatalog

LOGGER = logging.getLogger(__name__)


class ToolCandidate(BaseModel):
    name: str
    description: str
    code: str
    sample_input: dict
    origin: str = "generated"


class GeneratedToolCodePayload(BaseModel):
    code: str = ""


class ToolBuilderAgent:
    BANNED_CODE_PATTERNS = (
        "rm -",
        " os.remove(",
        "os.remove(",
        "shutil.rmtree(",
        "subprocess.run('rm",
        'subprocess.run("rm',
        "subprocess.Popen('rm",
        'subprocess.Popen("rm',
        "eval(",
        "exec(",
    )

    def __init__(
        self,
        llm: Optional[LLMProtocol] = None,
        catalog: Optional[BuiltinToolCatalog] = None,
    ) -> None:
        self.llm = llm
        self.catalog = catalog or BuiltinToolCatalog()

    def build_tool(
        self,
        *,
        subtask: SubtaskSpec,
        shared_task_description: str,
        feedback: Optional[str] = None,
    ) -> ToolCandidate:
        function_name = self._function_name(subtask.id)

        builtin = self.catalog.resolve(subtask=subtask, function_name=function_name)
        if builtin is not None:
            self._validate_generated_code(builtin.code)
            return ToolCandidate(
                name=function_name,
                description=builtin.description,
                code=builtin.code,
                sample_input=builtin.sample_input,
                origin="builtin",
            )

        if self.llm is not None:
            retry_feedback = feedback
            last_error: Optional[Exception] = None
            max_internal_llm_attempts = 2
            for llm_attempt in range(1, max_internal_llm_attempts + 1):
                try:
                    llm_code = self._build_with_llm(
                        function_name=function_name,
                        subtask_description=subtask.description,
                        shared_task_description=shared_task_description,
                        feedback=retry_feedback,
                    )
                    llm_code = self._sanitize_candidate_code(llm_code)
                    self._validate_generated_code(llm_code)
                    return ToolCandidate(
                        name=function_name,
                        description=subtask.description,
                        code=llm_code,
                        sample_input=self._sample_input_for(subtask.description),
                        origin="llm",
                    )
                except Exception as exc:
                    last_error = exc
                    retry_feedback = self._merge_builder_feedback(
                        prior_feedback=feedback,
                        current_feedback=(
                            "Previous candidate failed validation with error: "
                            f"{exc}. Regenerate fully valid Python code and avoid triple-quoted strings."
                        ),
                    )
                    if llm_attempt < max_internal_llm_attempts:
                        LOGGER.warning(
                            "ToolBuilderAgent retrying LLM generation for subtask '%s' after error: %s",
                            subtask.id,
                            exc,
                        )
                        continue
                    LOGGER.warning(
                        "ToolBuilderAgent fallback to template tool for subtask '%s': %s",
                        subtask.id,
                        last_error,
                    )

        template_code = self._template_code(
            function_name=function_name,
            subtask_description=subtask.description,
            feedback=feedback,
        )
        self._validate_generated_code(template_code)
        return ToolCandidate(
            name=function_name,
            description=subtask.description,
            code=template_code,
            sample_input=self._sample_input_for(subtask.description),
            origin="template",
        )

    def build_fallback_tool(self, *, subtask: SubtaskSpec) -> ToolCandidate:
        function_name = self._function_name(subtask.id)
        subtask_literal = json.dumps(str(subtask.description))
        code = dedent(
            f"""
            from typing import Any, Dict

            def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
                value = (
                    task_input.get("doc")
                    or task_input.get("text")
                    or task_input.get("query")
                    or str(task_input)
                )
                cleaned = " ".join(str(value).split()).strip()
                if not cleaned:
                    cleaned = {subtask_literal}
                result = ("Fallback output for: " + {subtask_literal} + ". " + cleaned)[:900]
                return {{
                    "tool": "{function_name}",
                    "status": "ok",
                    "result": result,
                }}
            """
        ).strip() + "\n"
        return ToolCandidate(
            name=function_name,
            description=f"Fallback tool for: {subtask.description}",
            code=code,
            sample_input=self._sample_input_for(subtask.description),
            origin="fallback",
        )

    def _build_with_llm(
        self,
        *,
        function_name: str,
        subtask_description: str,
        shared_task_description: str,
        feedback: Optional[str],
    ) -> str:
        prompt = f"""
Write a Python function with this exact signature:
def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:

Requirements:
- Return dict with keys: tool, status, result.
- No shell-delete commands.
- No eval/exec.
- Keep deterministic.
- Use only Python stdlib.
- Handle missing keys gracefully.
- Do not use triple-quoted strings or docstrings.
- You may use `safe_cli(command: str, user_message: Optional[str] = None) -> str` for non-destructive CLI calls.

Subtask:
{subtask_description}

Shared task:
{shared_task_description}

Verifier feedback (if any):
{feedback or "None"}

Return only valid Python code (imports + function), no markdown.
"""
        bound = invoke_bound_schema(self.llm, prompt=prompt, schema=GeneratedToolCodePayload)
        if bound is not None:
            candidate = self._extract_python(str(bound.code).strip())
            if candidate.strip():
                return candidate

        response = self.llm.invoke(prompt)
        text = getattr(response, "content", None)
        if text is None:
            text = str(response)
        if isinstance(text, list):
            text = " ".join(str(item) for item in text)
        return self._extract_python(str(text))

    def _template_code(
        self,
        *,
        function_name: str,
        subtask_description: str,
        feedback: Optional[str],
    ) -> str:
        lower = subtask_description.lower()
        if any(token in lower for token in ("current time", "date", "timestamp", "clock")):
            body = f"""
from datetime import datetime, timezone
from typing import Any, Dict

def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).astimezone().isoformat()
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": now,
    }}
"""
            return dedent(body).strip() + "\n"

        if any(token in lower for token in ("extract code", "code block", "markdown code", "fenced code")):
            body = f"""
import re
from typing import Any, Dict

def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    text = str(task_input.get("doc") or task_input.get("text") or "")
    pattern = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\\n(.*?)```", re.DOTALL)
    blocks = [chunk.strip() for chunk in pattern.findall(text) if chunk.strip()]
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": "\\n\\n".join(blocks),
    }}
"""
            return dedent(body).strip() + "\n"

        if any(token in lower for token in ("summarize", "summary", "compress")):
            body = f"""
from typing import Any, Dict

def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    text = str(task_input.get("doc") or task_input.get("text") or task_input.get("query") or "")
    cleaned = " ".join(text.split())
    summary = cleaned[:500]
    if summary:
        summary = "Summary: " + summary
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": summary,
    }}
"""
            return dedent(body).strip() + "\n"

        note = f"Verifier feedback: {feedback}" if feedback else "No verifier feedback."
        subtask_literal = json.dumps(str(subtask_description))
        note_literal = json.dumps(str(note))
        body = f"""
from typing import Any, Dict

def {function_name}(task_input: Dict[str, Any]) -> Dict[str, Any]:
    value = task_input.get("query") or task_input.get("doc") or task_input.get("text") or ""
    text = " ".join(str(value).split()).strip()
    if not text:
        text = {subtask_literal}
    text = text[:700]
    result = (
        "Task focus: " + {subtask_literal} + ". "
        "Processed output: " + text + ". "
        + {note_literal}
    )[:900]
    return {{
        "tool": "{function_name}",
        "status": "ok",
        "result": result,
    }}
"""
        return dedent(body).strip() + "\n"

    def _validate_generated_code(self, code: str) -> None:
        lower = code.lower()
        for pattern in self.BANNED_CODE_PATTERNS:
            if pattern in lower:
                raise ValueError(f"Generated code contains banned pattern: {pattern}")
        compile(code, "<tool_candidate>", "exec")

    @staticmethod
    def _function_name(subtask_id: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", subtask_id).strip("_").lower()
        if not sanitized:
            sanitized = "task"
        if sanitized[0].isdigit():
            sanitized = f"task_{sanitized}"
        sanitized = sanitized[:48].rstrip("_") or "task"
        return f"tool_{sanitized}"

    @staticmethod
    def _sample_input_for(subtask_description: str) -> dict:
        lower = subtask_description.lower()
        sample = {
            "query": "Example user request",
            "text": "Example input text",
            "doc": "# Sample\\n\\n```python\\nprint('hi')\\n```",
        }
        if "time" in lower:
            sample["query"] = "Return current time"
        return sample

    @staticmethod
    def _extract_python(text: str) -> str:
        stripped = str(text or "").strip()
        if not stripped:
            return ""

        blocks = re.findall(r"```(?:python)?\s*(.*?)```", stripped, re.DOTALL | re.I)
        if blocks:
            stripped = "\n\n".join(block.strip() for block in blocks if block.strip())

        lines = stripped.splitlines()
        start_idx = 0
        for idx, line in enumerate(lines):
            token = line.strip()
            if token.startswith(("from ", "import ", "def ")):
                start_idx = idx
                break
        stripped = "\n".join(lines[start_idx:]).strip()
        if not stripped:
            return ""
        return stripped + ("\n" if not stripped.endswith("\n") else "")

    @classmethod
    def _sanitize_candidate_code(cls, code: str) -> str:
        candidate = str(code or "").replace("\r\n", "\n").strip()
        if not candidate:
            raise ValueError("Empty candidate code.")
        candidate = cls._extract_python(candidate).strip()
        if not candidate:
            raise ValueError("No python code extracted from candidate.")

        try:
            compile(candidate, "<tool_candidate_precheck>", "exec")
        except SyntaxError as exc:
            lower_error = str(exc).lower()
            if "triple-quoted string literal" in lower_error:
                repaired = cls._repair_unterminated_triple_quotes(candidate)
                compile(repaired, "<tool_candidate_repaired>", "exec")
                return repaired + ("\n" if not repaired.endswith("\n") else "")
            raise
        return candidate + ("\n" if not candidate.endswith("\n") else "")

    @staticmethod
    def _repair_unterminated_triple_quotes(code: str) -> str:
        # Remove balanced triple-quoted blocks first.
        repaired = re.sub(r'"""[\s\S]*?"""', '""', code)
        repaired = re.sub(r"'''[\s\S]*?'''", "''", repaired)
        # Convert stray triple-quote tokens into single-quote tokens to avoid parser traps.
        if repaired.count('"""') % 2 != 0:
            repaired = repaired.replace('"""', '"')
        if repaired.count("'''") % 2 != 0:
            repaired = repaired.replace("'''", "'")
        fixed_lines = []
        for raw_line in repaired.splitlines():
            line = raw_line.rstrip()
            # If a line now has an unterminated plain string, force-close it.
            if line.count('"') % 2 != 0:
                line += '"'
            if line.count("'") % 2 != 0:
                line += "'"
            fixed_lines.append(line)
        return "\n".join(fixed_lines).strip()

    @staticmethod
    def _merge_builder_feedback(
        *,
        prior_feedback: Optional[str],
        current_feedback: str,
    ) -> str:
        first = str(prior_feedback or "").strip()
        second = str(current_feedback or "").strip()
        if first and second:
            return f"{first}\n\n{second}"
        return first or second
