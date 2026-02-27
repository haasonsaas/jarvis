"""Calendar next-event handler."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.integrations_calendar_common import (
    calendar_error_response,
)


def _services():
    from jarvis.tools import services as s

    return s


async def calendar_next_event(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _calendar_fetch_events = s._calendar_fetch_events
    CALENDAR_DEFAULT_WINDOW_HOURS = s.CALENDAR_DEFAULT_WINDOW_HOURS
    CALENDAR_MAX_WINDOW_HOURS = s.CALENDAR_MAX_WINDOW_HOURS

    start_time = time.monotonic()
    if not _tool_permitted("calendar_next_event"):
        record_summary("calendar_next_event", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("calendar_next_event", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    window_hours = _as_float(
        args.get("window_hours", CALENDAR_DEFAULT_WINDOW_HOURS),
        CALENDAR_DEFAULT_WINDOW_HOURS,
        minimum=0.1,
        maximum=CALENDAR_MAX_WINDOW_HOURS,
    )
    now = time.time()
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower() or None
    events, error_code = await _calendar_fetch_events(
        calendar_entity_id=calendar_entity_id,
        start_ts=now,
        end_ts=now + (window_hours * 3600.0),
    )
    if error_code is not None:
        _record_service_error("calendar_next_event", start_time, error_code)
        return calendar_error_response(error_code)
    if not events:
        record_summary("calendar_next_event", "empty", start_time)
        return {"content": [{"type": "text", "text": "No upcoming calendar events found."}]}
    event = events[0]
    start_value = float(event.get("start_ts", now))
    if bool(event.get("all_day")):
        when = time.strftime("%Y-%m-%d", time.localtime(start_value)) + " (all day)"
    else:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_value))
    summary = str(event.get("summary", "(untitled)"))
    entity = str(event.get("entity_id", "calendar"))
    location = str(event.get("location", "")).strip()
    location_text = f" at {location}" if location else ""
    record_summary("calendar_next_event", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Next event: {summary} on {when}{location_text} [{entity}]."}]}
