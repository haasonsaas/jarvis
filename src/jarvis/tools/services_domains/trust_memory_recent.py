"""Memory recent handler for trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def memory_recent(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _as_str_list = s._as_str_list
    _memory_requested_scopes = s._memory_requested_scopes
    _memory_entry_scope = s._memory_entry_scope
    _memory_visible_tags = s._memory_visible_tags
    _memory_confidence_score = s._memory_confidence_score
    _memory_confidence_label = s._memory_confidence_label
    _memory_source_trail = s._memory_source_trail

    start_time = time.monotonic()
    if not _tool_permitted("memory_recent"):
        record_summary("memory_recent", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_recent", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    kind = args.get("kind")
    source_list = _as_str_list(args.get("sources"))
    scoped_policy = _memory_requested_scopes(args.get("scopes"), query=str(args.get("query", "")))
    try:
        results = _memory.recent(limit=limit, kind=str(kind) if kind else None, sources=source_list)
    except Exception as e:
        _record_service_error("memory_recent", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory recent failed: {e}"}]}
    scoped_results = []
    for entry in results:
        if _memory_entry_scope(entry) in scoped_policy:
            scoped_results.append(entry)
        if len(scoped_results) >= limit:
            break
    results = scoped_results
    if not results:
        record_summary("memory_recent", "empty", start_time)
        return {"content": [{"type": "text", "text": f"No recent memories found in scopes={','.join(scoped_policy)}."}]}
    lines = [f"Retrieval policy scopes={','.join(scoped_policy)}"]
    now_ts = time.time()
    for entry in results:
        visible_tags = _memory_visible_tags(entry.tags)
        tags = f" tags={','.join(visible_tags)}" if visible_tags else ""
        snippet = entry.text[:200]
        confidence_score = _memory_confidence_score(entry, now_ts=now_ts)
        confidence_label = _memory_confidence_label(confidence_score)
        source = str(entry.source).strip() or "unknown"
        scope = _memory_entry_scope(entry)
        trail = _memory_source_trail(entry)
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} trail={trail} {snippet}{tags}"
        )
    record_summary("memory_recent", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
