"""Reminder handlers for planner domain."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.planner_runtime import (
    due_unnotified_reminder_payloads as _runtime_due_unnotified_reminder_payloads,
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


def _due_unnotified_reminder_payloads(*, limit: int, now_ts: float) -> list[dict[str, Any]]:
    s = _services()
    return _runtime_due_unnotified_reminder_payloads(
        memory=s._memory,
        reminders=s._reminders,
        limit=limit,
        now_ts=now_ts,
    )


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


async def reminder_notify_due(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _audit = s._audit
    _config = s._config
    _as_int = s._as_int
    _as_float = s._as_float
    _normalize_nudge_policy = s._normalize_nudge_policy
    _nudge_policy = s._nudge_policy
    _quiet_window_active = s._quiet_window_active
    pushover_notify = s.pushover_notify
    _memory = s._memory
    _reminders = s._reminders

    start_time = time.monotonic()
    if not _tool_permitted("reminder_notify_due"):
        record_summary("reminder_notify_due", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _tool_permitted("pushover_notify"):
        _record_service_error("reminder_notify_due", start_time, "policy")
        _audit("reminder_notify_due", {"result": "denied", "reason": "pushover_policy"})
        return {"content": [{"type": "text", "text": "Pushover notifications are disabled by policy."}]}
    if not _config or not str(_config.pushover_api_token).strip() or not str(_config.pushover_user_key).strip():
        _record_service_error("reminder_notify_due", start_time, "missing_config")
        _audit("reminder_notify_due", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    title = str(args.get("title", "Jarvis reminders")).strip() or "Jarvis reminders"
    now = time.time()
    try:
        due_payloads = _due_unnotified_reminder_payloads(limit=limit, now_ts=now)
    except Exception:
        _record_service_error("reminder_notify_due", start_time, "storage_error")
        return {
            "content": [
                {"type": "text", "text": "Reminder notification dispatch failed: persistent storage unavailable."}
            ]
        }
    if not due_payloads:
        record_summary("reminder_notify_due", "empty", start_time)
        _audit("reminder_notify_due", {"result": "empty", "limit": limit})
        return {"content": [{"type": "text", "text": "No due reminders awaiting notification."}]}

    policy = _normalize_nudge_policy(args.get("nudge_policy", _nudge_policy))
    quiet_active = _quiet_window_active(now_ts=now)
    deferred_count = 0
    dispatch_payloads = due_payloads
    if quiet_active and policy in {"defer", "adaptive"}:
        if policy == "defer":
            deferred_count = len(dispatch_payloads)
            dispatch_payloads = []
        else:
            urgent_overdue_sec = _as_float(
                args.get("urgent_overdue_sec", 3600.0),
                3600.0,
                minimum=60.0,
                maximum=86_400.0,
            )
            urgent_payloads: list[dict[str, Any]] = []
            for payload in dispatch_payloads:
                due_at = float(payload.get("due_at", now))
                overdue_sec = max(0.0, now - due_at)
                if overdue_sec >= urgent_overdue_sec:
                    urgent_payloads.append(payload)
            deferred_count = max(0, len(dispatch_payloads) - len(urgent_payloads))
            dispatch_payloads = urgent_payloads
    if not dispatch_payloads and deferred_count > 0:
        record_summary("reminder_notify_due", "deferred", start_time, effect=f"deferred={deferred_count}", risk="low")
        _audit(
            "reminder_notify_due",
            {
                "result": "deferred",
                "policy": policy,
                "quiet_window_active": quiet_active,
                "deferred_count": deferred_count,
                "limit": limit,
            },
        )
        return {"content": [{"type": "text", "text": f"Deferred {deferred_count} due reminder notifications until quiet hours end."}]}

    sent = 0
    failed = 0
    for payload in dispatch_payloads:
        reminder_id = int(payload.get("id", 0))
        text = str(payload.get("text", "")).strip() or "(untitled)"
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(payload.get("due_at", now))))
        notify_result = await pushover_notify(
            {"title": title, "priority": 0, "message": f"Reminder {reminder_id}: {text} (due {due_local})"}
        )
        notify_text = str(notify_result.get("content", [{}])[0].get("text", "")).strip().lower()
        if "notification sent" not in notify_text:
            failed += 1
            continue
        sent += 1
        if _memory is not None:
            try:
                _memory.mark_reminder_notified(reminder_id, notified_at=time.time())
            except Exception:
                failed += 1
                sent -= 1
                continue
        if reminder_id in _reminders:
            _reminders[reminder_id]["notified_at"] = time.time()
    if sent == 0 and failed > 0:
        _record_service_error("reminder_notify_due", start_time, "api_error")
        _audit(
            "reminder_notify_due",
            {
                "result": "api_error",
                "sent": sent,
                "failed": failed,
                "deferred_count": deferred_count,
                "policy": policy,
                "quiet_window_active": quiet_active,
            },
        )
        return {"content": [{"type": "text", "text": "Unable to send due reminder notifications."}]}
    record_summary("reminder_notify_due", "ok", start_time, effect=f"sent={sent}", risk="low")
    _audit(
        "reminder_notify_due",
        {
            "result": "ok",
            "sent": sent,
            "failed": failed,
            "deferred_count": deferred_count,
            "policy": policy,
            "quiet_window_active": quiet_active,
        },
    )
    suffix = f" ({failed} failed)." if failed else "."
    if deferred_count > 0:
        suffix += f" Deferred: {deferred_count}."
    return {"content": [{"type": "text", "text": f"Due reminder notifications sent: {sent}{suffix}"}]}


