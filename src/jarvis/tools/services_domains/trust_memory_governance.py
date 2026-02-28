"""Memory governance handlers for trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _parse_simple_assertion(text: str) -> tuple[str, str] | None:
    cleaned_chars: list[str] = []
    for ch in str(text or "").strip().lower():
        if ch.isalnum() or ch in {" ", "_", "-"}:
            cleaned_chars.append(ch)
        else:
            cleaned_chars.append(" ")
    normalized = " ".join("".join(cleaned_chars).split())
    if not normalized:
        return None
    tokens = normalized.split()
    if len(tokens) < 3:
        return None
    try:
        predicate_index = tokens.index("is")
    except ValueError:
        return None
    if predicate_index <= 0 or predicate_index >= (len(tokens) - 1):
        return None
    subject = " ".join(tokens[:predicate_index]).strip()
    remainder = tokens[predicate_index + 1 :]
    polarity_prefix = "yes:"
    if remainder and remainder[0] == "not":
        polarity_prefix = "not:"
        remainder = remainder[1:]
    value = " ".join(remainder).strip()
    if len(subject) < 2 or len(subject) > 80 or not value or len(value) > 80:
        return None
    return subject, f"{polarity_prefix}{value}"


def _memory_quality_audit(*, stale_days: float, limit: int) -> dict[str, Any]:
    s = _services()
    time = s.time
    _memory = s._memory

    if _memory is None:
        return {"error": "missing_store"}
    entries = _memory.recent(limit=limit, include_inactive=True)
    duplicates: list[dict[str, Any]] = []
    duplicate_ids: list[int] = []
    seen_by_text: dict[str, int] = {}
    stale_ids: list[int] = []
    contradictions: list[dict[str, Any]] = []
    assertions: dict[str, str] = {}
    now = time.time()
    stale_cutoff = now - (max(1.0, stale_days) * 86400.0)
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
        parsed = _parse_simple_assertion(str(entry.text))
        key = parsed[0] if parsed else ""
        value = parsed[1] if parsed else ""
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
            flush_payload = _memory.pre_compaction_flush(reason="governance_cleanup")
            for memory_id in candidate_ids:
                with suppress(Exception):
                    if _memory.delete_memory(memory_id):
                        removed += 1
        else:
            flush_payload = None
        payload = {
            "action": action,
            "apply": apply,
            "candidate_count": len(candidate_ids),
            "removed_count": removed,
            "candidate_ids": candidate_ids[:200],
            "pre_compaction_flush": flush_payload,
        }
        record_summary("memory_governance", "ok", start_time, effect="cleanup_applied" if apply else "cleanup_preview", risk="low")
        return _expansion_payload_response(payload)

    if action == "doctor":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        try:
            payload = {
                "action": action,
                "doctor": _memory.memory_doctor(),
            }
        except Exception as exc:
            _record_service_error("memory_governance", start_time, "storage_error")
            return {"content": [{"type": "text", "text": f"Memory doctor failed: {exc}"}]}
        record_summary("memory_governance", "ok", start_time, effect="doctor", risk="low")
        return _expansion_payload_response(payload)

    if action == "graph":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        limit = _as_int(args.get("limit", 200), 200, minimum=1, maximum=1000)
        include_inactive = _as_bool(args.get("include_inactive"), default=False)
        try:
            snapshot = _memory.entity_graph_snapshot(limit=limit, include_inactive=include_inactive)
        except Exception as exc:
            _record_service_error("memory_governance", start_time, "storage_error")
            return {"content": [{"type": "text", "text": f"Memory graph failed: {exc}"}]}
        payload = {
            "action": action,
            "include_inactive": include_inactive,
            "graph": snapshot,
        }
        record_summary("memory_governance", "ok", start_time, effect="graph", risk="low")
        return _expansion_payload_response(payload)

    if action == "compaction_flush":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        try:
            payload = {
                "action": action,
                "flush": _memory.pre_compaction_flush(reason="manual"),
            }
        except Exception as exc:
            _record_service_error("memory_governance", start_time, "storage_error")
            return {"content": [{"type": "text", "text": f"Compaction flush failed: {exc}"}]}
        record_summary("memory_governance", "ok", start_time, effect="compaction_flush", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("memory_governance", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown memory_governance action."}]}
