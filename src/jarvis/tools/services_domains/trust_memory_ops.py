"""Memory mutation handlers for trust domain."""

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

