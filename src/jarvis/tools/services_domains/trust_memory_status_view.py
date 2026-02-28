"""Memory status handler for trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def memory_status(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    MEMORY_SCOPES = s.MEMORY_SCOPES
    MEMORY_SCOPE_TAG_PREFIX = s.MEMORY_SCOPE_TAG_PREFIX
    MEMORY_QUERY_SCOPE_HINTS = s.MEMORY_QUERY_SCOPE_HINTS
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("memory_status"):
        record_summary("memory_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_status", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    try:
        if _as_bool(args.get("warm"), default=False):
            _memory.warm()
        if _as_bool(args.get("sync"), default=False):
            _memory.sync()
        if _as_bool(args.get("optimize"), default=False):
            _memory.optimize()
        if _as_bool(args.get("vacuum"), default=False):
            _memory.vacuum()
        status = _memory.memory_status()
        if isinstance(status, dict):
            if _as_bool(args.get("doctor"), default=False):
                status["doctor"] = _memory.memory_doctor()
            if _as_bool(args.get("include_graph"), default=False):
                status["entity_graph_snapshot"] = _memory.entity_graph_snapshot(limit=200, include_inactive=False)
            status["confidence_model"] = {
                "version": "v1",
                "inputs": ["retrieval_score", "recency", "source", "sensitivity"],
            }
            status["scope_policy"] = {
                "supported_scopes": sorted(MEMORY_SCOPES),
                "tag_prefix": MEMORY_SCOPE_TAG_PREFIX,
                "query_hints": {scope: sorted(hints) for scope, hints in MEMORY_QUERY_SCOPE_HINTS.items()},
                "default_scope": "preferences",
            }
    except Exception as e:
        _record_service_error("memory_status", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory status failed: {e}"}]}
    record_summary("memory_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status)}]}
