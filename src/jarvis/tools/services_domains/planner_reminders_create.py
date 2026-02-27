"""Reminder creation handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def reminder_create(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _parse_due_timestamp = s._parse_due_timestamp
    _reminder_status = s._reminder_status
    REMINDER_MAX_ACTIVE = s.REMINDER_MAX_ACTIVE
    _memory = s._memory
    _allocate_reminder_id = s._allocate_reminder_id
    _reminders = s._reminders
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("reminder_create"):
        record_summary("reminder_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("reminder_create", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Reminder text is required."}]}
    now = time.time()
    due_at = _parse_due_timestamp(args.get("due"), now_ts=now)
    if due_at is None:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Reminder due value must be epoch seconds, ISO datetime, or a relative duration like 'in 20m'.",
                }
            ]
        }
    if due_at <= now:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Reminder due time must be in the future."}]}
    pending_count = int(_reminder_status().get("pending_count", 0))
    if pending_count >= REMINDER_MAX_ACTIVE:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Too many pending reminders ({REMINDER_MAX_ACTIVE} max)."}]}

    reminder_id: int
    if _memory is not None:
        try:
            reminder_id = _memory.add_reminder(text=text, due_at=due_at, created_at=now)
        except Exception:
            _record_service_error("reminder_create", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Reminder create failed: persistent storage unavailable."}]}
    else:
        reminder_id = _allocate_reminder_id()
    _reminders[reminder_id] = {
        "id": reminder_id,
        "text": text,
        "due_at": due_at,
        "created_at": now,
        "status": "pending",
        "completed_at": None,
        "notified_at": None,
    }
    due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_at))
    record_summary("reminder_create", "ok", start_time, effect=f"reminder_id={reminder_id}", risk="low")
    _audit(
        "reminder_create",
        {
            "result": "ok",
            "reminder_id": reminder_id,
            "text_length": len(text),
            "due_at": due_at,
        },
    )
    return {"content": [{"type": "text", "text": f"Reminder {reminder_id} set for {due_local}."}]}
