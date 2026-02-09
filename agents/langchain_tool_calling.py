"""
Optional LangChain tool-calling helpers with graceful fallback.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional, Type, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


def supports_tool_binding(llm: Any) -> bool:
    return llm is not None and hasattr(llm, "bind_tools")


def invoke_bound_schema(
    llm: Any,
    *,
    prompt: str,
    schema: Type[TModel],
    tool_choice: str = "any",
) -> Optional[TModel]:
    """
    Invoke an LLM with a bound pydantic schema tool and return validated args.
    Returns None when binding is unsupported or parsing fails.
    """
    if not supports_tool_binding(llm):
        return None

    try:
        bound = _bind_tools(llm, schema=schema, tool_choice=tool_choice)
        response = bound.invoke(prompt)
    except Exception:
        return None

    for raw_args in _iter_tool_args(response):
        payload = _coerce_payload(raw_args)
        if payload is None:
            continue
        validated = _validate_schema(schema, payload)
        if validated is not None:
            return validated

    # Fallback: some models may return JSON content without tool_calls.
    content = getattr(response, "content", None)
    if isinstance(content, str):
        payload = _coerce_payload(content)
        if payload is not None:
            return _validate_schema(schema, payload)

    return None


def _bind_tools(llm: Any, *, schema: Type[TModel], tool_choice: str) -> Any:
    try:
        return llm.bind_tools([schema], tool_choice=tool_choice)
    except TypeError:
        # Older adapters may not accept tool_choice kwarg.
        return llm.bind_tools([schema])


def _iter_tool_args(response: Any) -> Iterable[Any]:
    tool_calls = getattr(response, "tool_calls", None)
    if isinstance(tool_calls, list):
        for call in tool_calls:
            extracted = _extract_args(call)
            if extracted is not None:
                yield extracted

    additional = getattr(response, "additional_kwargs", None)
    if isinstance(additional, dict):
        nested = additional.get("tool_calls")
        if isinstance(nested, list):
            for call in nested:
                extracted = _extract_args(call)
                if extracted is not None:
                    yield extracted


def _extract_args(call: Any) -> Optional[Any]:
    if isinstance(call, dict):
        if "args" in call:
            return call.get("args")
        if "arguments" in call:
            return call.get("arguments")
        function_obj = call.get("function")
        if isinstance(function_obj, dict):
            if "arguments" in function_obj:
                return function_obj.get("arguments")
            if "args" in function_obj:
                return function_obj.get("args")
        return None

    args_attr = getattr(call, "args", None)
    if args_attr is not None:
        return args_attr
    arguments_attr = getattr(call, "arguments", None)
    if arguments_attr is not None:
        return arguments_attr
    function_attr = getattr(call, "function", None)
    if isinstance(function_attr, dict):
        if "arguments" in function_attr:
            return function_attr.get("arguments")
        if "args" in function_attr:
            return function_attr.get("args")
    return None


def _coerce_payload(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _validate_schema(schema: Type[TModel], payload: Dict[str, Any]) -> Optional[TModel]:
    try:
        if hasattr(schema, "model_validate"):
            return schema.model_validate(payload)
        return schema.parse_obj(payload)  # pragma: no cover - pydantic v1 fallback
    except Exception:
        return None

