"""Home Assistant timer handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def home_assistant_timer(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    re = s.re
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile
    _ha_get_state = s._ha_get_state
    _duration_seconds = s._duration_seconds
    _recovery_operation = s._recovery_operation
    _ha_call_service = s._ha_call_service

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_timer"):
        record_summary("home_assistant_timer", "denied", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_timer", start_time, "missing_config")
        _audit("home_assistant_timer", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"state", "start", "pause", "cancel", "finish"}:
        _record_service_error("home_assistant_timer", start_time, "invalid_data")
        _audit("home_assistant_timer", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: state, start, pause, cancel, finish."}]}
    if not entity_id:
        _record_service_error("home_assistant_timer", start_time, "missing_fields")
        _audit("home_assistant_timer", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_timer",
        args,
        mutating=(action != "state"),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit(
            "home_assistant_timer",
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
    if _home_permission_profile == "readonly" and action != "state":
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "state":
        payload, error_code = await _ha_get_state(entity_id)
        if error_code is not None:
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"Timer not found: {entity_id}"}]}
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        body = payload or {}
        attributes = body.get("attributes", {}) if isinstance(body, dict) else {}
        result = {
            "entity_id": entity_id,
            "state": body.get("state", "unknown") if isinstance(body, dict) else "unknown",
            "remaining": attributes.get("remaining") if isinstance(attributes, dict) else None,
            "duration": attributes.get("duration") if isinstance(attributes, dict) else None,
            "finishes_at": attributes.get("finishes_at") if isinstance(attributes, dict) else None,
        }
        record_summary("home_assistant_timer", "ok", start_time)
        _audit("home_assistant_timer", {"result": "ok", "action": action, "entity_id": entity_id})
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    service_map = {
        "start": "start",
        "pause": "pause",
        "cancel": "cancel",
        "finish": "finish",
    }
    service_data: dict[str, Any] = {"entity_id": entity_id}
    if action == "start":
        duration_text = str(args.get("duration", "")).strip()
        if duration_text:
            duration_seconds = _duration_seconds(duration_text)
            if duration_seconds is not None:
                total = max(1, int(round(duration_seconds)))
                hours, rem = divmod(total, 3600)
                minutes, seconds = divmod(rem, 60)
                service_data["duration"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            elif re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", duration_text):
                service_data["duration"] = duration_text
            else:
                _record_service_error("home_assistant_timer", start_time, "invalid_data")
                _audit("home_assistant_timer", {"result": "invalid_data", "field": "duration"})
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "duration must be HH:MM:SS or a relative duration like 5m.",
                        }
                    ]
                }
    with _recovery_operation(
        "home_assistant_timer",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("timer", service_map[action], service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant timer entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        recovery.mark_completed(detail="ok", context={"duration": service_data.get("duration")})
        record_summary("home_assistant_timer", "ok", start_time)
        _audit(
            "home_assistant_timer",
            {"result": "ok", "action": action, "entity_id": entity_id, "duration": service_data.get("duration")},
        )
        return {"content": [{"type": "text", "text": f"Home Assistant timer action executed: {action} on {entity_id}."}]}

