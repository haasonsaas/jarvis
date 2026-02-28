"""Memory search handler for trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _as_float = s._as_float
    _config = s._config
    _as_bool = s._as_bool
    _as_str_list = s._as_str_list
    _memory_requested_scopes = s._memory_requested_scopes
    _memory_entry_scope = s._memory_entry_scope
    _memory_visible_tags = s._memory_visible_tags
    _memory_confidence_score = s._memory_confidence_score
    _memory_confidence_label = s._memory_confidence_label
    _memory_source_trail = s._memory_source_trail

    start_time = time.monotonic()
    if not _tool_permitted("memory_search"):
        record_summary("memory_search", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_search", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    query = str(args.get("query", "")).strip()
    if not query:
        _record_service_error("memory_search", start_time, "missing_query")
        return {"content": [{"type": "text", "text": "Search query required."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    default_max_sensitivity = _as_float(
        getattr(_config, "memory_max_sensitivity", 0.4),
        0.4,
        minimum=0.0,
        maximum=1.0,
    )
    default_hybrid_weight = _as_float(
        getattr(_config, "memory_hybrid_weight", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    default_decay_enabled = _as_bool(getattr(_config, "memory_decay_enabled", False), default=False)
    default_decay_half_life_days = _as_float(
        getattr(_config, "memory_decay_half_life_days", 30.0),
        30.0,
        minimum=0.1,
    )
    default_mmr_enabled = _as_bool(getattr(_config, "memory_mmr_enabled", False), default=False)
    default_mmr_lambda = _as_float(
        getattr(_config, "memory_mmr_lambda", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    include_sensitive = _as_bool(args.get("include_sensitive"), default=False)
    include_inactive = _as_bool(args.get("include_inactive"), default=False)
    max_sensitivity = None if include_sensitive else _as_float(
        args.get("max_sensitivity", default_max_sensitivity),
        default_max_sensitivity,
        minimum=0.0,
        maximum=1.0,
    )
    source_list = _as_str_list(args.get("sources"))
    scoped_policy = _memory_requested_scopes(args.get("scopes"), query=query)
    try:
        results = _memory.search_v2(
            query,
            limit=limit,
            max_sensitivity=max_sensitivity,
            hybrid_weight=_as_float(
                args.get("hybrid_weight", default_hybrid_weight),
                default_hybrid_weight,
                minimum=0.0,
                maximum=1.0,
            ),
            decay_enabled=_as_bool(args.get("decay_enabled"), default=default_decay_enabled),
            decay_half_life_days=_as_float(
                args.get("decay_half_life_days", default_decay_half_life_days),
                default_decay_half_life_days,
                minimum=0.1,
            ),
            mmr_enabled=_as_bool(args.get("mmr_enabled"), default=default_mmr_enabled),
            mmr_lambda=_as_float(
                args.get("mmr_lambda", default_mmr_lambda),
                default_mmr_lambda,
                minimum=0.0,
                maximum=1.0,
            ),
            sources=source_list,
            include_inactive=include_inactive,
        )
    except Exception as e:
        _record_service_error("memory_search", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory search failed: {e}"}]}
    scoped_results = []
    for entry in results:
        if _memory_entry_scope(entry) in scoped_policy:
            scoped_results.append(entry)
        if len(scoped_results) >= limit:
            break
    results = scoped_results
    if not results:
        record_summary("memory_search", "empty", start_time)
        return {"content": [{"type": "text", "text": f"No relevant memories found in scopes={','.join(scoped_policy)}."}]}
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
        validity = ""
        if entry.valid_to is not None:
            validity = f" valid_to={entry.valid_to:.0f}"
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} score={entry.score:.2f} trail={trail}{validity} {snippet}{tags}"
        )
    record_summary("memory_search", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
