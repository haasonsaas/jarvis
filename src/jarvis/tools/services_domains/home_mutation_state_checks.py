"""State and cooldown checks for smart-home mutation preflight."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_mutation_prepare_state(
    context: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _cooldown_active = s._cooldown_active
    _ha_get_state = s._ha_get_state

    from jarvis.tools.robot import tool_feedback

    domain = str(context.get("domain", "")).strip().lower()
    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()
    dry_run = bool(context.get("dry_run", False))

    if dry_run:
        return context, None

    if _cooldown_active(domain, action, entity_id):
        tool_feedback("done")
        record_summary("smart_home", "cooldown", start_time)
        return None, {"content": [{"type": "text", "text": "Action cooldown active. Try again in a moment."}]}

    state_payload, state_error = await _ha_get_state(entity_id)
    if state_error is not None:
        _record_service_error("smart_home", start_time, state_error)
        if state_error == "not_found":
            return None, {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if state_error == "auth":
            return None, {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if state_error == "timeout":
            return None, {"content": [{"type": "text", "text": "Home Assistant state preflight timed out."}]}
        if state_error == "cancelled":
            return None, {"content": [{"type": "text", "text": "Home Assistant state preflight was cancelled."}]}
        if state_error == "circuit_open":
            return None, {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if state_error == "network_client_error":
            return None, {"content": [{"type": "text", "text": "Failed to reach Home Assistant for state preflight."}]}
        return None, {"content": [{"type": "text", "text": "Unable to validate entity state before action."}]}

    current_state = str(state_payload.get("state", "unknown")) if isinstance(state_payload, dict) else "unknown"
    if action == "turn_on" and current_state not in {"off", "unavailable", "unknown"}:
        record_summary("smart_home", "noop", start_time, effect=f"already_on {entity_id}", risk="low")
        return None, {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}
    if action == "turn_off" and current_state == "off":
        record_summary("smart_home", "noop", start_time, effect=f"already_off {entity_id}", risk="low")
        return None, {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}

    context["current_state"] = current_state
    return context, None
