"""Tool summary handlers for governance domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def tool_summary(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    list_summaries = s.list_summaries
    _record_service_error = s._record_service_error
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("tool_summary"):
        record_summary("tool_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
    except Exception as e:
        _record_service_error("tool_summary", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(summaries, default=str)}]}


async def tool_summary_text(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    list_summaries = s.list_summaries
    _format_tool_summaries = s._format_tool_summaries
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("tool_summary_text"):
        record_summary("tool_summary_text", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 6), 6, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
        text = _format_tool_summaries(summaries)
    except Exception as e:
        _record_service_error("tool_summary_text", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary_text", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}
