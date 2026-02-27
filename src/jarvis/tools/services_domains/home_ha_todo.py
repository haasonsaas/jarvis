"""Home Assistant to-do handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def home_assistant_todo(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile
    _ha_call_service = s._ha_call_service
    _collect_json_lists_by_key = s._collect_json_lists_by_key
    _recovery_operation = s._recovery_operation

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_todo"):
        record_summary("home_assistant_todo", "denied", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_todo", start_time, "missing_config")
        _audit("home_assistant_todo", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"list", "add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "invalid_data")
        _audit("home_assistant_todo", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: list, add, remove."}]}
    if not entity_id:
        _record_service_error("home_assistant_todo", start_time, "missing_fields")
        _audit("home_assistant_todo", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_todo",
        args,
        mutating=(action in {"add", "remove"}),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit(
            "home_assistant_todo",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action in {"add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "list":
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

