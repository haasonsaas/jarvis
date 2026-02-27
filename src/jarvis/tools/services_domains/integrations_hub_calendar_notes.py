"""Calendar and notes handlers for integration hub."""

from __future__ import annotations

import re
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def integration_hub_calendar_upsert(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _ha_call_service = s._ha_call_service
    _expansion_payload_response = s._expansion_payload_response
    _config = s._config

    if not _as_bool(args.get("confirm"), default=False):
        _record_service_error("integration_hub", start_time, "confirm_required")
        return {"content": [{"type": "text", "text": "calendar_upsert requires confirm=true."}]}
    event = args.get("event") if isinstance(args.get("event"), dict) else {}
    calendar_entity_id = (
        str(args.get("calendar_entity_id", "")).strip()
        or str(event.get("calendar_entity_id", "")).strip()
        or str(event.get("entity_id", "")).strip()
    ).lower()
    summary = str(args.get("summary", "")).strip() or str(event.get("summary", "")).strip()
    description = str(args.get("description", "")).strip() or str(event.get("description", "")).strip()
    location = str(args.get("location", "")).strip() or str(event.get("location", "")).strip()
    start_value = (
        str(args.get("start", "")).strip()
        or str(event.get("start_date_time", "")).strip()
        or str(event.get("start", "")).strip()
        or str(event.get("start_date", "")).strip()
    )
    end_value = (
        str(args.get("end", "")).strip()
        or str(event.get("end_date_time", "")).strip()
        or str(event.get("end", "")).strip()
        or str(event.get("end_date", "")).strip()
    )
    if not summary or not start_value or not end_value:
        _record_service_error("integration_hub", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "calendar_upsert requires summary, start, and end values."}]}
    service_data: dict[str, Any] = {"summary": summary}
    if calendar_entity_id:
        service_data["entity_id"] = calendar_entity_id
    if description:
        service_data["description"] = description
    if location:
        service_data["location"] = location
    is_all_day = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_value)) and bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_value)
    )
    if is_all_day:
        service_data["start_date"] = start_value
        service_data["end_date"] = end_value
    else:
        service_data["start_date_time"] = start_value
        service_data["end_date_time"] = end_value
    if _config is not None and _config.has_home_assistant:
        _, error_code = await _ha_call_service("calendar", "create_event", service_data)
        if error_code is not None:
            _record_service_error("integration_hub", start_time, error_code)
            return {"content": [{"type": "text", "text": f"calendar_upsert failed: {error_code}."}]}
        payload = {
            "action": "calendar_upsert",
            "status": "executed",
            "provider": "home_assistant",
            "calendar_entity_id": calendar_entity_id,
            "service_data": service_data,
        }
    else:
        payload = {
            "action": "calendar_upsert",
            "status": "drafted",
            "provider": "none",
            "service_data": service_data,
            "detail": "Home Assistant is not configured; returning draft payload.",
        }
    record_summary("integration_hub", "ok", start_time, effect="calendar_upsert", risk="medium")
    return _expansion_payload_response(payload)


async def integration_hub_calendar_delete(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _ha_call_service = s._ha_call_service
    _expansion_payload_response = s._expansion_payload_response
    _config = s._config

    if not _as_bool(args.get("confirm"), default=False):
        _record_service_error("integration_hub", start_time, "confirm_required")
        return {"content": [{"type": "text", "text": "calendar_delete requires confirm=true."}]}
    event_id = str(args.get("event_id", "")).strip()
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower()
    if not event_id:
        _record_service_error("integration_hub", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "calendar_delete requires event_id."}]}
    service_data: dict[str, Any] = {"event_id": event_id}
    if calendar_entity_id:
        service_data["entity_id"] = calendar_entity_id
    if _config is not None and _config.has_home_assistant:
        _, error_code = await _ha_call_service("calendar", "delete_event", service_data)
        if error_code is not None:
            _record_service_error("integration_hub", start_time, error_code)
            return {"content": [{"type": "text", "text": f"calendar_delete failed: {error_code}."}]}
        payload = {
            "action": "calendar_delete",
            "status": "executed",
            "provider": "home_assistant",
            "service_data": service_data,
        }
    else:
        payload = {
            "action": "calendar_delete",
            "status": "drafted",
            "provider": "none",
            "service_data": service_data,
            "detail": "Home Assistant is not configured; returning draft payload.",
        }
    record_summary("integration_hub", "ok", start_time, effect="calendar_delete", risk="high")
    return _expansion_payload_response(payload)


async def integration_hub_notes_capture(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _capture_note_notion = s._capture_note_notion
    _capture_note = s._capture_note
    _expansion_payload_response = s._expansion_payload_response

    backend = str(args.get("backend", "local_markdown")).strip().lower() or "local_markdown"
    title = str(args.get("title", "Jarvis Note")).strip() or "Jarvis Note"
    content = str(args.get("content", "")).strip()
    if not content:
        _record_service_error("integration_hub", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "content is required for notes_capture."}]}
    if backend == "notion":
        notion_payload, notion_error = await _capture_note_notion(title=title, content=content)
        if notion_error is None and isinstance(notion_payload, dict):
            captured = notion_payload
        elif notion_error == "missing_config":
            captured = _capture_note(
                backend=backend,
                title=title,
                content=content,
                path_hint=str(args.get("path", "")).strip(),
            )
        else:
            _record_service_error("integration_hub", start_time, notion_error or "unexpected")
            return {"content": [{"type": "text", "text": f"Notion notes_capture failed: {notion_error or 'unexpected'}."}]}
    else:
        captured = _capture_note(
            backend=backend,
            title=title,
            content=content,
            path_hint=str(args.get("path", "")).strip(),
        )
    payload = {"action": "notes_capture", **captured}
    record_summary("integration_hub", "ok", start_time, effect=f"notes:{backend}", risk="low")
    return _expansion_payload_response(payload)
