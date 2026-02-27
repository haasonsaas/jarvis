"""Communications, integrations, and scheduler schema fragments."""

from __future__ import annotations

from typing import Any

SERVICE_TOOL_SCHEMAS_COMMS: dict[str, dict[str, Any]] = {
    "weather_lookup": {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "units": {"type": "string", "description": "metric or imperial"},
        },
        "required": ["location"],
    },
    "webhook_trigger": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "payload": {"type": "object"},
            "headers": {"type": "object"},
            "timeout_sec": {"type": "number"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
            "preview_only": {"type": "boolean"},
            "preview_token": {"type": "string"},
            "require_preview_ack": {"type": "boolean"},
        },
        "required": ["url"],
    },
    "webhook_inbound_list": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "webhook_inbound_clear": {
        "type": "object",
        "properties": {},
    },
    "slack_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["message"],
    },
    "discord_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["message"],
    },
    "email_send": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "confirm": {"type": "boolean"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
            "preview_only": {"type": "boolean"},
            "preview_token": {"type": "string"},
            "require_preview_ack": {"type": "boolean"},
        },
        "required": ["subject", "body"],
    },
    "email_summary": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "dead_letter_list": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "status": {"type": "string"},
        },
    },
    "dead_letter_replay": {
        "type": "object",
        "properties": {
            "entry_id": {"type": "string"},
            "limit": {"type": "integer"},
            "status": {"type": "string"},
        },
    },
    "timer_create": {
        "type": "object",
        "properties": {
            "duration": {
                "description": "Duration in seconds (number) or string like '90s', '5m', '1h 15m'.",
            },
            "label": {"type": "string"},
        },
        "required": ["duration"],
    },
    "timer_list": {
        "type": "object",
        "properties": {
            "include_expired": {"type": "boolean"},
        },
    },
    "timer_cancel": {
        "type": "object",
        "properties": {
            "timer_id": {"type": "integer"},
            "label": {"type": "string"},
        },
    },
    "reminder_create": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "due": {
                "description": "Due timestamp as epoch seconds, ISO datetime, or relative duration like 'in 20m' / '45m'.",
            },
        },
        "required": ["text", "due"],
    },
    "reminder_list": {
        "type": "object",
        "properties": {
            "include_completed": {"type": "boolean"},
            "limit": {"type": "integer"},
        },
    },
    "reminder_complete": {
        "type": "object",
        "properties": {
            "reminder_id": {"type": "integer"},
        },
        "required": ["reminder_id"],
    },
    "reminder_notify_due": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "title": {"type": "string"},
            "nudge_policy": {"type": "string", "description": "interrupt, defer, or adaptive (optional override)."},
            "urgent_overdue_sec": {"type": "number", "description": "When nudge_policy=adaptive and quiet hours are active, overdue reminders beyond this threshold still send."},
        },
    },
    "calendar_events": {
        "type": "object",
        "properties": {
            "calendar_entity_id": {"type": "string"},
            "start": {"type": "string", "description": "Optional start datetime (ISO)."},
            "end": {"type": "string", "description": "Optional end datetime (ISO)."},
            "window_hours": {"type": "number", "description": "Window size when end is omitted."},
            "limit": {"type": "integer"},
        },
    },
    "calendar_next_event": {
        "type": "object",
        "properties": {
            "calendar_entity_id": {"type": "string"},
            "window_hours": {"type": "number"},
        },
    },
    "todoist_add_task": {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "description": {"type": "string"},
            "due_string": {"type": "string"},
            "priority": {"type": "integer"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["content"],
    },
    "todoist_list_tasks": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "format": {"type": "string", "description": "short (default) or verbose"},
        },
    },
    "pushover_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "title": {"type": "string"},
            "priority": {"type": "integer"},
        },
        "required": ["message"],
    },
    "get_time": {},
    "system_status": {},
    "system_status_contract": {},
    "jarvis_scorecard": {},
}
