"""Memory and memory-governance handlers extracted from trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _memory_pii_guardrails_enabled = s._memory_pii_guardrails_enabled
    _contains_pii = s._contains_pii
    _as_float = s._as_float
    _normalize_memory_scope = s._normalize_memory_scope
    MEMORY_SCOPES = s.MEMORY_SCOPES
    _memory_scope_for_add = s._memory_scope_for_add
    _memory_scope_tags = s._memory_scope_tags

    start_time = time.monotonic()
    if not _tool_permitted("memory_add"):
        record_summary("memory_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_add", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    allow_pii = _as_bool(args.get("allow_pii"), default=False)
    if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
        _record_service_error("memory_add", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Potential PII detected in memory text. Use allow_pii=true only when intentional.",
                }
            ]
        }
    tags_raw = args.get("tags")
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    kind = str(args.get("kind", "note"))
    importance = _as_float(args.get("importance", 0.5), 0.5, minimum=0.0, maximum=1.0)
    sensitivity = _as_float(args.get("sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    source = str(args.get("source", "user"))
    requested_scope = args.get("scope")
    if requested_scope is not None and _normalize_memory_scope(requested_scope) is None:
        _record_service_error("memory_add", start_time, "invalid_data")
        scopes_text = ", ".join(sorted(MEMORY_SCOPES))
        return {"content": [{"type": "text", "text": f"scope must be one of: {scopes_text}."}]}
    scope = _memory_scope_for_add(kind=kind, source=source, tags=tags, requested_scope=requested_scope)
    tags = _memory_scope_tags(tags, scope)
    try:
        memory_id = _memory.add_memory(
            text,
            kind=kind,
            tags=tags,
            importance=importance,
            sensitivity=sensitivity,
            source=source,
        )
    except Exception as e:
        _record_service_error("memory_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory add failed: {e}"}]}
    record_summary("memory_add", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Memory stored (id={memory_id}, scope={scope})."}]}


async def memory_update(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int
    _as_bool = s._as_bool
    _memory_pii_guardrails_enabled = s._memory_pii_guardrails_enabled
    _contains_pii = s._contains_pii

    start_time = time.monotonic()
    if not _tool_permitted("memory_update"):
        record_summary("memory_update", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_update", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    memory_id = _as_exact_int(args.get("memory_id"))
    if memory_id is None or memory_id <= 0:
        _record_service_error("memory_update", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "memory_id must be a positive integer."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_update", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    allow_pii = _as_bool(args.get("allow_pii"), default=False)
    if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
        _record_service_error("memory_update", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Potential PII detected in memory text. Use allow_pii=true only when intentional.",
                }
            ]
        }
    try:
        updated = _memory.update_memory_text(memory_id, text)
    except Exception as e:
        _record_service_error("memory_update", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory update failed: {e}"}]}
    if not updated:
        _record_service_error("memory_update", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Memory not found."}]}
    record_summary("memory_update", "ok", start_time, effect=f"memory_id={memory_id}", risk="low")
    return {"content": [{"type": "text", "text": f"Memory updated (id={memory_id})."}]}


async def memory_forget(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int

    start_time = time.monotonic()
    if not _tool_permitted("memory_forget"):
        record_summary("memory_forget", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_forget", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    memory_id = _as_exact_int(args.get("memory_id"))
    if memory_id is None or memory_id <= 0:
        _record_service_error("memory_forget", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "memory_id must be a positive integer."}]}
    try:
        deleted = _memory.delete_memory(memory_id)
    except Exception as e:
        _record_service_error("memory_forget", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory forget failed: {e}"}]}
    if not deleted:
        _record_service_error("memory_forget", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Memory not found."}]}
    record_summary("memory_forget", "ok", start_time, effect=f"memory_id={memory_id}", risk="low")
    return {"content": [{"type": "text", "text": f"Memory forgotten (id={memory_id})."}]}


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
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} score={entry.score:.2f} trail={trail} {snippet}{tags}"
        )
    record_summary("memory_search", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


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


def _memory_quality_audit(*, stale_days: float, limit: int) -> dict[str, Any]:
    s = _services()
    time = s.time
    re = s.re
    _memory = s._memory

    if _memory is None:
        return {"error": "missing_store"}
    entries = _memory.recent(limit=limit)
    duplicates: list[dict[str, Any]] = []
    duplicate_ids: list[int] = []
    seen_by_text: dict[str, int] = {}
    stale_ids: list[int] = []
    contradictions: list[dict[str, Any]] = []
    assertions: dict[str, str] = {}
    now = time.time()
    stale_cutoff = now - (max(1.0, stale_days) * 86400.0)
    is_not_re = re.compile(r"^\s*(?P<subject>[a-z0-9 _-]{2,})\s+is\s+not\s+(?P<value>[a-z0-9 _-]{1,80})\s*$", re.IGNORECASE)
    is_re = re.compile(r"^\s*(?P<subject>[a-z0-9 _-]{2,})\s+is\s+(?P<value>[a-z0-9 _-]{1,80})\s*$", re.IGNORECASE)
    for entry in entries:
        text_key = " ".join(str(entry.text).strip().lower().split())
        if text_key:
            prior_id = seen_by_text.get(text_key)
            if prior_id is None:
                seen_by_text[text_key] = int(entry.id)
            else:
                duplicate_ids.append(int(entry.id))
                duplicates.append({"memory_id": int(entry.id), "duplicate_of": int(prior_id)})
        if float(entry.created_at) < stale_cutoff:
            stale_ids.append(int(entry.id))
        text = str(entry.text).strip().lower()
        neg = is_not_re.match(text)
        pos = is_re.match(text)
        if neg:
            key = neg.group("subject").strip()
            value = f"not:{neg.group('value').strip()}"
        elif pos:
            key = pos.group("subject").strip()
            value = f"yes:{pos.group('value').strip()}"
        else:
            key = ""
            value = ""
        if key:
            previous = assertions.get(key)
            if previous is not None and previous != value:
                contradictions.append({"subject": key, "previous": previous, "current": value, "memory_id": int(entry.id)})
            assertions[key] = value
    return {
        "scanned": len(entries),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates[:100],
        "duplicate_ids": duplicate_ids,
        "stale_count": len(stale_ids),
        "stale_ids": stale_ids[:200],
        "contradiction_count": len(contradictions),
        "contradictions": contradictions[:50],
        "stale_days": stale_days,
    }

async def memory_governance(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    suppress = s.suppress
    MEMORY_SCOPES = s.MEMORY_SCOPES
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _identity_default_user = s._identity_default_user
    _as_str_list = s._as_str_list
    _memory_partition_overlays = s._memory_partition_overlays
    _expansion_payload_response = s._expansion_payload_response
    _as_float = s._as_float
    _as_int = s._as_int
    _memory_quality_last = s._memory_quality_last
    _as_bool = s._as_bool
    _memory = s._memory

    start_time = time.monotonic()
    if not _tool_permitted("memory_governance"):
        record_summary("memory_governance", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "partition":
        user = str(args.get("user", _identity_default_user)).strip().lower() or _identity_default_user
        shared_scopes = [scope for scope in _as_str_list(args.get("shared_scopes"), lower=True) if scope in MEMORY_SCOPES]
        private_scopes = [scope for scope in _as_str_list(args.get("private_scopes"), lower=True) if scope in MEMORY_SCOPES]
        if not private_scopes:
            private_scopes = sorted(MEMORY_SCOPES)
        _memory_partition_overlays[user] = {
            "user": user,
            "shared_scopes": sorted(set(shared_scopes)),
            "private_scopes": sorted(set(private_scopes)),
            "updated_at": time.time(),
        }
        payload = {
            "action": action,
            "overlay": dict(_memory_partition_overlays[user]),
            "overlay_count": len(_memory_partition_overlays),
        }
        record_summary("memory_governance", "ok", start_time, effect="partition_updated", risk="low")
        return _expansion_payload_response(payload)

    if action == "quality_audit":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        stale_days = _as_float(args.get("stale_days", 90.0), 90.0, minimum=1.0, maximum=3650.0)
        limit = _as_int(args.get("limit", 300), 300, minimum=10, maximum=1000)
        try:
            report = _memory_quality_audit(stale_days=stale_days, limit=limit)
        except Exception as exc:
            _record_service_error("memory_governance", start_time, "storage_error")
            return {"content": [{"type": "text", "text": f"Memory quality audit failed: {exc}"}]}
        report["action"] = action
        report["generated_at"] = time.time()
        _memory_quality_last.clear()
        _memory_quality_last.update(report)
        record_summary("memory_governance", "ok", start_time, effect="quality_audit", risk="low")
        return _expansion_payload_response(report)

    if action == "cleanup":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        apply = _as_bool(args.get("apply"), default=False)
        duplicate_ids = [int(item) for item in _memory_quality_last.get("duplicate_ids", []) if isinstance(item, int)]
        stale_ids = [int(item) for item in _memory_quality_last.get("stale_ids", []) if isinstance(item, int)]
        candidate_ids = sorted(set(duplicate_ids + stale_ids))
        removed = 0
        if apply:
            for memory_id in candidate_ids:
                with suppress(Exception):
                    if _memory.delete_memory(memory_id):
                        removed += 1
        payload = {
            "action": action,
            "apply": apply,
            "candidate_count": len(candidate_ids),
            "removed_count": removed,
            "candidate_ids": candidate_ids[:200],
        }
        record_summary("memory_governance", "ok", start_time, effect="cleanup_applied" if apply else "cleanup_preview", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("memory_governance", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown memory_governance action."}]}

