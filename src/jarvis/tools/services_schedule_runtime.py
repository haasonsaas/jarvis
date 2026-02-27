"""Scheduling and datetime helper runtime helpers for services domains."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def duration_seconds(services_module: Any, value: Any) -> float | None:
    s = services_module
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0.0:
            return None
        return min(seconds, s.TIMER_MAX_SECONDS)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    try:
        parsed = float(text)
        if math.isfinite(parsed) and parsed > 0.0:
            return min(parsed, s.TIMER_MAX_SECONDS)
    except ValueError:
        pass
    total = 0.0
    cursor = 0
    for match in s._DURATION_SEGMENT_RE.finditer(text):
        if match.start() != cursor and text[cursor : match.start()].strip():
            return None
        value_part = float(match.group("value"))
        unit = match.group("unit").lower()
        if unit.startswith("h"):
            total += value_part * 3600.0
        elif unit.startswith("m"):
            total += value_part * 60.0
        else:
            total += value_part
        cursor = match.end()
    if cursor != len(text) and text[cursor:].strip():
        return None
    if total <= 0.0:
        return None
    return min(total, s.TIMER_MAX_SECONDS)


def local_timezone() -> Any:
    tz = datetime.now().astimezone().tzinfo
    return tz if tz is not None else timezone.utc


def parse_datetime_text(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone())
    return parsed


def parse_due_timestamp(services_module: Any, value: Any, *, now_ts: float | None = None) -> float | None:
    s = services_module
    now = s.time.time() if now_ts is None else float(now_ts)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidate = float(value)
        if not math.isfinite(candidate) or candidate <= 0.0:
            return None
        if candidate >= 1_000_000_000.0:
            return candidate
        return now + min(candidate, s.TIMER_MAX_SECONDS)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    numeric = None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and math.isfinite(numeric) and numeric > 0.0:
        if numeric >= 1_000_000_000.0:
            return numeric
        return now + min(numeric, s.TIMER_MAX_SECONDS)
    if lowered.startswith("in "):
        relative = duration_seconds(s, lowered[3:])
        if relative is not None:
            return now + relative
    relative = duration_seconds(s, text)
    if relative is not None:
        return now + relative
    parsed = parse_datetime_text(text)
    if parsed is None:
        return None
    return parsed.timestamp()


def timestamp_to_iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def format_duration(seconds: float) -> str:
    remaining = max(0, int(round(seconds)))
    hours, rem = divmod(remaining, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


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
