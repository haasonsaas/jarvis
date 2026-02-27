"""Add/remove actions for Home Assistant to-do tool."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_assistant_todo_mutate(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _audit = s._audit
    _record_service_error = s._record_service_error
    _ha_call_service = s._ha_call_service
    _recovery_operation = s._recovery_operation

    args = context.get("args") if isinstance(context.get("args"), dict) else {}
    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()

    item = str(args.get("item", "")).strip()
    item_id = str(args.get("item_id", "")).strip()
    if action == "add":
        if not item:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item is required when action=add."}]}
        service = "add_item"
        service_data = {"entity_id": entity_id, "item": item}
        success_text = "Added Home Assistant to-do item."
    else:
        if not item and not item_id:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item or item_id is required when action=remove."}]}
        service = "remove_item"
        service_data = {"entity_id": entity_id, "item": item_id or item}
        success_text = "Removed Home Assistant to-do item."

    with _recovery_operation(
        "home_assistant_todo",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("todo", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant to-do entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {
                "result": "ok",
                "action": action,
                "entity_id": entity_id,
                "item_length": len(item),
                "item_id": item_id,
            },
        )
        return {"content": [{"type": "text", "text": success_text}]}
