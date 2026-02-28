"""Helpers for adapting Jarvis async handlers into OpenAI Agents function tools."""

from __future__ import annotations

import math
import json
from typing import Any, Awaitable, Callable

from agents import FunctionTool
from agents.tool_context import ToolContext

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _normalize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(schema, dict) and schema.get("type") == "object":
        return schema
    properties = schema.get("properties") if isinstance(schema, dict) else None
    required = schema.get("required") if isinstance(schema, dict) else None
    normalized: dict[str, Any] = {"type": "object"}
    if isinstance(properties, dict):
        normalized["properties"] = properties
    if isinstance(required, list):
        normalized["required"] = [str(item) for item in required]
    return normalized


def _matches_schema_type(value: Any, expected: str) -> bool:
    kind = str(expected or "").strip().lower()
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return math.isfinite(float(value))
        return False
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "null":
        return value is None
    return True


def _validate_args_against_schema(
    value: Any,
    schema: dict[str, Any] | None,
    *,
    path: str,
) -> str | None:
    if not isinstance(schema, dict):
        return None

    schema_type = schema.get("type")
    expected_types: list[str] = []
    if isinstance(schema_type, str):
        expected_types = [schema_type]
    elif isinstance(schema_type, list):
        expected_types = [str(item) for item in schema_type if isinstance(item, str)]
    if expected_types and not any(_matches_schema_type(value, item) for item in expected_types):
        expected = " | ".join(expected_types)
        return f"Invalid tool arguments: field {path} must be {expected}."

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        return f"Invalid tool arguments: field {path} must be one of {enum_values}."

    if isinstance(value, dict):
        properties = schema.get("properties")
        required = schema.get("required")
        property_map = properties if isinstance(properties, dict) else {}
        required_keys = [item for item in required if isinstance(item, str)] if isinstance(required, list) else []
        for key in required_keys:
            if key not in value:
                return f"Invalid tool arguments: missing required field {path}.{key}."
        allow_unknown = bool(schema.get("additionalProperties", False))
        for key, item in value.items():
            child_path = f"{path}.{key}"
            child_schema = property_map.get(key)
            if child_schema is None:
                if not allow_unknown:
                    return f"Invalid tool arguments: unexpected field {child_path}."
                continue
            child_error = _validate_args_against_schema(item, child_schema, path=child_path)
            if child_error:
                return child_error
        return None

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value[:64]):
                child_error = _validate_args_against_schema(item, item_schema, path=f"{path}[{index}]")
                if child_error:
                    return child_error
    return None


def tool_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        lines: list[str] = []
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type", "")).strip().lower() != "text":
                    continue
                text = str(item.get("text", "")).strip()
                if text:
                    lines.append(text)
        remainder = {k: v for k, v in result.items() if k != "content"}
        if lines and not remainder:
            return "\n".join(lines)
        if lines and remainder:
            lines.append(json.dumps(remainder, default=str))
            return "\n".join(lines)
        return json.dumps(result, default=str)
    return json.dumps(result, default=str)


def build_function_tool(
    *,
    name: str,
    description: str,
    schema: dict[str, Any] | None,
    handler: ToolHandler,
) -> FunctionTool:
    params_schema = _normalize_schema(schema or {})

    async def _invoke(_ctx: ToolContext[Any], args_json: str) -> str:
        raw = str(args_json or "").strip()
        if not raw:
            parsed: dict[str, Any] = {}
        else:
            try:
                payload = json.loads(raw)
            except Exception:
                return "Invalid tool arguments: expected a JSON object."
            if not isinstance(payload, dict):
                return "Invalid tool arguments: expected a JSON object."
            parsed = payload
        validation_error = _validate_args_against_schema(parsed, params_schema, path="args")
        if validation_error:
            return validation_error
        try:
            result = await handler(parsed)
        except Exception:
            # Keep failure text stable and avoid leaking tool internals to the model.
            return f"Tool {name} failed."
        return tool_result_text(result)

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=params_schema,
        on_invoke_tool=_invoke,
        strict_json_schema=False,
    )
