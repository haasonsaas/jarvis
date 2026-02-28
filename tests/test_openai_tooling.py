from __future__ import annotations

import json

import pytest

from jarvis.tools.openai_tooling import build_function_tool, tool_result_text


def test_tool_result_text_prefers_text_content_and_serializes_remainder() -> None:
    result = {
        "content": [
            {"type": "text", "text": "first"},
            {"type": "input_image", "image_url": "https://example.com/x.png"},
            {"type": "text", "text": "second"},
        ],
        "meta": {"k": "v"},
    }
    text = tool_result_text(result)
    assert text.startswith("first\nsecond\n")
    assert json.loads(text.splitlines()[-1]) == {"meta": {"k": "v"}}


@pytest.mark.asyncio
async def test_build_function_tool_invokes_handler_and_normalizes_schema() -> None:
    calls: list[dict[str, object]] = []

    async def _handler(args: dict[str, object]) -> dict[str, object]:
        calls.append(dict(args))
        return {"content": [{"type": "text", "text": "ok"}]}

    tool = build_function_tool(
        name="demo_tool",
        description="demo",
        schema={"properties": {"x": {"type": "string"}}, "required": ["x"]},
        handler=_handler,
    )

    text = await tool.on_invoke_tool(None, '{"x":"value"}')
    assert text == "ok"
    assert calls == [{"x": "value"}]
    assert tool.params_json_schema["type"] == "object"
    assert tool.params_json_schema["required"] == ["x"]
    assert tool.params_json_schema["properties"]["x"]["type"] == "string"


@pytest.mark.asyncio
async def test_build_function_tool_rejects_non_object_args() -> None:
    async def _handler(args: dict[str, object]) -> dict[str, object]:
        return {"args": args}

    tool = build_function_tool(
        name="demo_tool",
        description="demo",
        schema={"type": "object"},
        handler=_handler,
    )

    assert json.loads(await tool.on_invoke_tool(None, "")) == {"args": {}}
    assert "expected a JSON object" in (await tool.on_invoke_tool(None, "[]"))
    assert "expected a JSON object" in (await tool.on_invoke_tool(None, "{not-json"))


@pytest.mark.asyncio
async def test_build_function_tool_validates_required_types_and_unknown_fields() -> None:
    async def _handler(args: dict[str, object]) -> dict[str, object]:
        return {"args": args}

    tool = build_function_tool(
        name="typed_tool",
        description="demo",
        schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "flag": {"type": "boolean"},
            },
            "required": ["count"],
        },
        handler=_handler,
    )

    missing = await tool.on_invoke_tool(None, "{}")
    assert "missing required field args.count" in missing
    bad_type = await tool.on_invoke_tool(None, '{"count":"x"}')
    assert "field args.count must be integer" in bad_type
    unknown = await tool.on_invoke_tool(None, '{"count":1,"extra":true}')
    assert "unexpected field args.extra" in unknown
    ok = await tool.on_invoke_tool(None, '{"count":2,"flag":false}')
    assert json.loads(ok) == {"args": {"count": 2, "flag": False}}


@pytest.mark.asyncio
async def test_build_function_tool_hides_internal_exception_details() -> None:
    async def _handler(_args: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("secret payload should not leak")

    tool = build_function_tool(
        name="sensitive_tool",
        description="demo",
        schema={"type": "object"},
        handler=_handler,
    )

    text = await tool.on_invoke_tool(None, "{}")
    assert text == "Tool sensitive_tool failed."
    assert "secret payload" not in text
