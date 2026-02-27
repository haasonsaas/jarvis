"""Memory summary handlers for trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def memory_summary_add(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_add"):
        record_summary("memory_summary_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    topic = str(args.get("topic", "")).strip()
    summary = str(args.get("summary", "")).strip()
    if not topic or not summary:
        _record_service_error("memory_summary_add", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Summary topic and text required."}]}
    try:
        _memory.upsert_summary(topic, summary)
    except Exception as e:
        _record_service_error("memory_summary_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary add failed: {e}"}]}
    record_summary("memory_summary_add", "ok", start_time)
    return {"content": [{"type": "text", "text": "Summary stored."}]}


async def memory_summary_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_int = s._as_int

    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_list"):
        record_summary("memory_summary_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    try:
        results = _memory.list_summaries(limit=limit)
    except Exception as e:
        _record_service_error("memory_summary_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary list failed: {e}"}]}
    if not results:
        record_summary("memory_summary_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No summaries found."}]}
    lines = [f"{summary.topic}: {summary.summary}" for summary in results]
    record_summary("memory_summary_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}

