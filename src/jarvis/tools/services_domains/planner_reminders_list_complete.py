"""Reminder list and complete handlers."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.planner_runtime import (
    list_reminder_payloads as _runtime_list_reminder_payloads,
)


def _services():
    from jarvis.tools import services as s

    return s


def _list_reminder_payloads(*, include_completed: bool, limit: int, now_ts: float) -> list[dict[str, Any]]:
    s = _services()
    return _runtime_list_reminder_payloads(
        memory=s._memory,
        reminders=s._reminders,
        include_completed=include_completed,
        limit=limit,
        now_ts=now_ts,
    )


async def reminder_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _as_bool = s._as_bool
    _as_int = s._as_int
    _record_service_error = s._record_service_error
    _format_duration = s._format_duration
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("reminder_list"):
        record_summary("reminder_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    include_completed = _as_bool(args.get("include_completed"), default=False)
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=100)
    now = time.time()
    try:
        payloads = _list_reminder_payloads(include_completed=include_completed, limit=limit, now_ts=now)
    except Exception:
        _record_service_error("reminder_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": "Reminder list failed: persistent storage unavailable."}]}
    if not payloads:
        record_summary("reminder_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No reminders found."}]}
    lines: list[str] = []
    for payload in payloads:
        reminder_id = int(payload.get("id", 0))
        text = str(payload.get("text", "")).strip() or "(untitled)"
        status = str(payload.get("status", "pending"))
        due_at = float(payload.get("due_at", now))
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_at))
        if status == "completed":
            completed_at = payload.get("completed_at")
            completed_local = (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(completed_at)))
                if completed_at is not None
                else "unknown"
            )
            lines.append(f"- {reminder_id}: {text} (completed at {completed_local}; due at {due_local})")
            continue
        remaining = due_at - now
        if remaining <= 0.0:
            when_text = f"overdue by {_format_duration(abs(remaining))}"
        else:
            when_text = f"due in {_format_duration(remaining)}"
        lines.append(f"- {reminder_id}: {text} ({when_text}; at {due_local})")
    record_summary("reminder_list", "ok", start_time)
    _audit(
        "reminder_list",
        {"result": "ok", "count": len(lines), "include_completed": include_completed},
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def reminder_complete(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _as_exact_int = s._as_exact_int
    _record_service_error = s._record_service_error
    _memory = s._memory
    _reminders = s._reminders
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("reminder_complete"):
        record_summary("reminder_complete", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    reminder_id = _as_exact_int(args.get("reminder_id"))
    if reminder_id is None or reminder_id <= 0:
        _record_service_error("reminder_complete", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "reminder_id must be a positive integer."}]}
    if _memory is not None:
        try:
            completed = _memory.complete_reminder(reminder_id)
        except Exception:
            _record_service_error("reminder_complete", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Reminder complete failed: persistent storage unavailable."}]}
        if not completed:
            _record_service_error("reminder_complete", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Reminder not found."}]}
    else:
        payload = _reminders.get(reminder_id)
        if payload is None or str(payload.get("status", "pending")) != "pending":
            _record_service_error("reminder_complete", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Reminder not found."}]}
        payload["status"] = "completed"
        payload["completed_at"] = time.time()
    if reminder_id in _reminders:
        _reminders[reminder_id]["status"] = "completed"
        _reminders[reminder_id]["completed_at"] = time.time()
    record_summary("reminder_complete", "ok", start_time, effect=f"reminder_id={reminder_id}", risk="low")
    _audit("reminder_complete", {"result": "ok", "reminder_id": reminder_id})
    return {"content": [{"type": "text", "text": f"Completed reminder {reminder_id}."}]}
