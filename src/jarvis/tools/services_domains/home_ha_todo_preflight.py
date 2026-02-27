"""Preflight checks for Home Assistant to-do actions."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def home_assistant_todo_prepare(
    args: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile

    if not _tool_permitted("home_assistant_todo"):
        record_summary("home_assistant_todo", "denied", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "policy"})
        return None, {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_todo", start_time, "missing_config")
        _audit("home_assistant_todo", {"result": "missing_config"})
        return None, {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"list", "add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "invalid_data")
        _audit("home_assistant_todo", {"result": "invalid_data", "field": "action"})
        return None, {"content": [{"type": "text", "text": "Action must be one of: list, add, remove."}]}
    if not entity_id:
        _record_service_error("home_assistant_todo", start_time, "missing_fields")
        _audit("home_assistant_todo", {"result": "missing_fields"})
        return None, {"content": [{"type": "text", "text": "entity_id is required."}]}
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
        return None, {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action in {"add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "readonly_profile", "action": action})
        return None, {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly.",
                }
            ]
        }

    return {
        "args": args,
        "action": action,
        "entity_id": entity_id,
        "identity_context": identity_context,
        "identity_chain": identity_chain,
    }, None
