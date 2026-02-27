"""Calendar list-events handler."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.integrations_calendar_common import (
    calendar_error_response,
    parse_calendar_window,
)


def _services():
    from jarvis.tools import services as s

    return s


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
    start_ts, end_ts = parse_calendar_window(args)
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
        return calendar_error_response(error_code)
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
