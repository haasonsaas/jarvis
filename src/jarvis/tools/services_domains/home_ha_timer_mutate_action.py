"""Mutating actions for Home Assistant timer tool."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _looks_like_hhmmss(value: str) -> bool:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 3:
        return False
    hour, minute, second = parts
    if not (hour.isdigit() and minute.isdigit() and second.isdigit()):
        return False
    if len(minute) != 2 or len(second) != 2 or len(hour) not in {1, 2}:
        return False
    hour_value = int(hour)
    minute_value = int(minute)
    second_value = int(second)
    return 0 <= hour_value <= 99 and 0 <= minute_value <= 59 and 0 <= second_value <= 59


async def home_assistant_timer_mutate(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _audit = s._audit
    _record_service_error = s._record_service_error
    _duration_seconds = s._duration_seconds
    _recovery_operation = s._recovery_operation
    _ha_call_service = s._ha_call_service

    args = context.get("args") if isinstance(context.get("args"), dict) else {}
    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()

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
            elif _looks_like_hhmmss(duration_text):
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
