"""List action for Home Assistant to-do tool."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_assistant_todo_list(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _audit = s._audit
    _record_service_error = s._record_service_error
    _ha_call_service = s._ha_call_service
    _collect_json_lists_by_key = s._collect_json_lists_by_key

    args = context.get("args") if isinstance(context.get("args"), dict) else {}
    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()

    payload, error_code = await _ha_call_service(
        "todo",
        "get_items",
        {
            "entity_id": entity_id,
            **(
                {"status": str(args.get("status", "")).strip()}
                if str(args.get("status", "")).strip()
                else {}
            ),
        },
        return_response=True,
    )
    if error_code is not None:
        _record_service_error("home_assistant_todo", start_time, error_code)
        _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": f"To-do entity or service not found: {entity_id}"}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
    items = [item for item in _collect_json_lists_by_key(payload, "items") if isinstance(item, dict)]
    if not items:
        record_summary("home_assistant_todo", "empty", start_time)
        _audit("home_assistant_todo", {"result": "empty", "action": action, "entity_id": entity_id})
        return {"content": [{"type": "text", "text": "No Home Assistant to-do items found."}]}
    lines: list[str] = []
    for item in items:
        summary = str(item.get("summary") or item.get("item") or "").strip() or "(untitled)"
        uid = str(item.get("uid") or item.get("id") or "").strip()
        status = str(item.get("status", "")).strip()
        due = str(item.get("due") or item.get("due_datetime") or "").strip()
        meta: list[str] = []
        if uid:
            meta.append(f"id={uid}")
        if status:
            meta.append(f"status={status}")
        if due:
            meta.append(f"due={due}")
        lines.append(f"- {summary}" + (f" ({'; '.join(meta)})" if meta else ""))
    record_summary("home_assistant_todo", "ok", start_time)
    _audit(
        "home_assistant_todo",
        {"result": "ok", "action": action, "entity_id": entity_id, "count": len(lines)},
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
