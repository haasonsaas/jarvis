"""Reminder due-notification handler."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.planner_runtime import (
    due_unnotified_reminder_payloads as _runtime_due_unnotified_reminder_payloads,
)


def _services():
    from jarvis.tools import services as s

    return s


def _due_unnotified_reminder_payloads(*, limit: int, now_ts: float) -> list[dict[str, Any]]:
    s = _services()
    return _runtime_due_unnotified_reminder_payloads(
        memory=s._memory,
        reminders=s._reminders,
        limit=limit,
        now_ts=now_ts,
    )


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
