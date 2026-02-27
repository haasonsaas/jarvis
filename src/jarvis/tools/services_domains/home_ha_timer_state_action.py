"""State action for Home Assistant timer tool."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_assistant_timer_state(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    _audit = s._audit
    _record_service_error = s._record_service_error
    _ha_get_state = s._ha_get_state

    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()

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
