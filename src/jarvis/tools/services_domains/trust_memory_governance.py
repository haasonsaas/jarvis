"""Memory governance handlers for trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

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

