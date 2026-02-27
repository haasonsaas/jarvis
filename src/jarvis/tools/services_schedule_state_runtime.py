"""Scheduling state/id/load helpers for services domains."""

from __future__ import annotations

from typing import Any

def allocate_timer_id(services_module: Any) -> int:
    s = services_module
    timer_id = s._timer_id_seq
    s._timer_id_seq += 1
    return timer_id


def allocate_reminder_id(services_module: Any) -> int:
    s = services_module
    reminder_id = s._reminder_id_seq
    s._reminder_id_seq += 1
    return reminder_id


def prune_timers(services_module: Any, now_mono: float | None = None) -> None:
    s = services_module
    if s._memory is not None:
        try:
            s._memory.expire_timers(now=s.time.time())
        except Exception:
            s.log.warning("Failed to expire persisted timers", exc_info=True)
    if not s._timers:
        return
    current = s.time.monotonic() if now_mono is None else now_mono
    expired = [timer_id for timer_id, payload in s._timers.items() if float(payload.get("due_mono", 0.0)) <= current]
    for timer_id in expired:
        s._timers.pop(timer_id, None)


def timer_status(services_module: Any) -> dict[str, Any]:
    s = services_module
    prune_timers(s)
    if not s._timers:
        return {"active_count": 0, "next_due_in_sec": None}
    now = s.time.monotonic()
    next_due = min(float(payload.get("due_mono", now)) for payload in s._timers.values())
    return {
        "active_count": len(s._timers),
        "next_due_in_sec": max(0.0, next_due - now),
    }


def load_timers_from_store(services_module: Any) -> None:
    s = services_module
    if s._memory is None:
        return
    now_wall = s.time.time()
    now_mono = s.time.monotonic()
    try:
        s._memory.expire_timers(now=now_wall)
        rows = s._memory.list_timers(status="active", include_expired=False, now=now_wall, limit=s.TIMER_MAX_ACTIVE)
    except Exception:
        s.log.warning("Failed to load persisted timers", exc_info=True)
        return
    max_id = 0
    for row in rows:
        remaining = float(row.due_at) - now_wall
        if remaining <= 0.0:
            continue
        timer_id = int(row.id)
        max_id = max(max_id, timer_id)
        s._timers[timer_id] = {
            "id": timer_id,
            "label": row.label,
            "duration_sec": float(row.duration_sec),
            "created_at": float(row.created_at),
            "due_at": float(row.due_at),
            "due_mono": now_mono + remaining,
        }
    if max_id >= s._timer_id_seq:
        s._timer_id_seq = max_id + 1


def reminder_status(services_module: Any) -> dict[str, Any]:
    s = services_module
    now = s.time.time()
    if s._memory is not None:
        try:
            counts = s._memory.reminder_counts()
            pending = s._memory.list_reminders(status="pending", now=now, limit=s.REMINDER_MAX_ACTIVE)
        except Exception:
            return {"pending_count": 0, "completed_count": 0, "due_count": 0, "next_due_in_sec": None}
        due_count = sum(1 for entry in pending if float(entry.due_at) <= now)
        next_due_in = None
        if pending:
            next_due = min(float(entry.due_at) for entry in pending)
            next_due_in = max(0.0, next_due - now)
        return {
            "pending_count": int(counts.get("pending", 0)),
            "completed_count": int(counts.get("completed", 0)),
            "due_count": int(due_count),
            "next_due_in_sec": next_due_in,
        }
    pending = [payload for payload in s._reminders.values() if str(payload.get("status", "pending")) == "pending"]
    completed_count = sum(
        1 for payload in s._reminders.values() if str(payload.get("status", "pending")) == "completed"
    )
    due_count = sum(1 for payload in pending if float(payload.get("due_at", 0.0)) <= now)
    next_due_in = None
    if pending:
        next_due = min(float(payload.get("due_at", now)) for payload in pending)
        next_due_in = max(0.0, next_due - now)
    return {
        "pending_count": len(pending),
        "completed_count": int(completed_count),
        "due_count": int(due_count),
        "next_due_in_sec": next_due_in,
    }


def load_reminders_from_store(services_module: Any) -> None:
    s = services_module
    if s._memory is None:
        return
    now = s.time.time()
    try:
        pending = s._memory.list_reminders(status="pending", now=now, limit=s.REMINDER_MAX_ACTIVE)
        completed = s._memory.list_reminders(status="completed", limit=s.REMINDER_MAX_ACTIVE)
    except Exception:
        s.log.warning("Failed to load persisted reminders", exc_info=True)
        return
    max_id = 0
    for row in [*pending, *completed]:
        reminder_id = int(row.id)
        max_id = max(max_id, reminder_id)
        s._reminders[reminder_id] = {
            "id": reminder_id,
            "text": str(row.text),
            "due_at": float(row.due_at),
            "created_at": float(row.created_at),
            "status": str(row.status),
            "completed_at": float(row.completed_at) if row.completed_at is not None else None,
            "notified_at": float(row.notified_at) if row.notified_at is not None else None,
        }
    if max_id >= s._reminder_id_seq:
        s._reminder_id_seq = max_id + 1
