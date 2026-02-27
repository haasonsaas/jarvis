"""Calendar integration handlers."""

from __future__ import annotations

import re
from typing import Any

from jarvis.tools.services_domains.integrations_runtime import (
    parse_calendar_window as _runtime_parse_calendar_window,
)


def _services():
    from jarvis.tools import services as s

    return s

async def _calendar_fetch_events(
    *,
    calendar_entity_id: str | None,
    start_ts: float,
    end_ts: float,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    s = _services()
    _timestamp_to_iso_utc = s._timestamp_to_iso_utc
    _ha_get_json = s._ha_get_json
    _parse_calendar_event_timestamp = s._parse_calendar_event_timestamp

    params = {"start": _timestamp_to_iso_utc(start_ts), "end": _timestamp_to_iso_utc(end_ts)}
    entity_ids: list[str]
    if calendar_entity_id:
        entity_ids = [calendar_entity_id]
    else:
        calendars_payload, calendars_error = await _ha_get_json("/api/calendars")
        if calendars_error is not None:
            return None, calendars_error
        if not isinstance(calendars_payload, list):
            return None, "invalid_json"
        entity_ids = []
        for item in calendars_payload:
            if not isinstance(item, dict):
                continue
            entity = str(item.get("entity_id", "")).strip().lower()
            if entity:
                entity_ids.append(entity)
        if not entity_ids:
            return [], None
    events: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        payload, error_code = await _ha_get_json(f"/api/calendars/{entity_id}", params=params)
        if error_code is not None:
            return None, error_code
        if not isinstance(payload, list):
            return None, "invalid_json"
        for item in payload:
            if not isinstance(item, dict):
                continue
            start_raw = item.get("start")
            start_event = _parse_calendar_event_timestamp(start_raw)
            if start_event is None:
                continue
            end_event = _parse_calendar_event_timestamp(item.get("end"))
            all_day = isinstance(start_raw, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_raw.strip()))
            events.append(
                {
                    "entity_id": entity_id,
                    "summary": str(item.get("summary", "")).strip() or "(untitled)",
                    "location": str(item.get("location", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                    "start": start_raw,
                    "end": item.get("end"),
                    "start_ts": start_event,
                    "end_ts": end_event,
                    "all_day": all_day,
                }
            )
    events.sort(key=lambda event: float(event.get("start_ts", start_ts)))
    return events, None


def _parse_calendar_window(args: dict[str, Any]) -> tuple[float | None, float | None]:
    s = _services()
    time = s.time
    _parse_due_timestamp = s._parse_due_timestamp
    _as_float = s._as_float
    CALENDAR_DEFAULT_WINDOW_HOURS = s.CALENDAR_DEFAULT_WINDOW_HOURS
    CALENDAR_MAX_WINDOW_HOURS = s.CALENDAR_MAX_WINDOW_HOURS

    now = time.time()
    return _runtime_parse_calendar_window(
        args,
        now_ts=now,
        parse_due_timestamp=lambda value: _parse_due_timestamp(value, now_ts=now),
        as_float=lambda value, default: _as_float(
            value,
            default,
            minimum=0.1,
            maximum=CALENDAR_MAX_WINDOW_HOURS,
        ),
        default_window_hours=CALENDAR_DEFAULT_WINDOW_HOURS,
        max_window_hours=CALENDAR_MAX_WINDOW_HOURS,
    )


async def calendar_events(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _calendar_fetch_events = s._calendar_fetch_events

    start_time = time.monotonic()
    if not _tool_permitted("calendar_events"):
        record_summary("calendar_events", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("calendar_events", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    start_ts, end_ts = _parse_calendar_window(args)
    if start_ts is None or end_ts is None:
        _record_service_error("calendar_events", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid calendar window. Use valid ISO timestamps or relative durations for start/end.",
                }
            ]
        }
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=100)
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower() or None
    events, error_code = await _calendar_fetch_events(
        calendar_entity_id=calendar_entity_id,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    if error_code is not None:
        _record_service_error("calendar_events", start_time, error_code)
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Calendar endpoint or entity not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Calendar request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Calendar request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant calendar endpoint."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant calendar response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant calendar error."}]}
    rows = (events or [])[:limit]
    if not rows:
        record_summary("calendar_events", "empty", start_time)
        return {"content": [{"type": "text", "text": "No calendar events found in the selected window."}]}
    lines: list[str] = []
    for event in rows:
        start_value = float(event.get("start_ts", start_ts))
        if bool(event.get("all_day")):
            when = time.strftime("%Y-%m-%d", time.localtime(start_value)) + " (all day)"
        else:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_value))
        summary = str(event.get("summary", "(untitled)"))
        entity = str(event.get("entity_id", "calendar"))
        location = str(event.get("location", "")).strip()
        location_text = f" @ {location}" if location else ""
        lines.append(f"- {when} | {summary} [{entity}]{location_text}")
    record_summary("calendar_events", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


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
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Calendar endpoint or entity not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Calendar request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Calendar request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant calendar endpoint."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant calendar response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant calendar error."}]}
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
