"""Timer creation handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def timer_create(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _duration_seconds = s._duration_seconds
    _record_service_error = s._record_service_error
    _prune_timers = s._prune_timers
    _timers = s._timers
    TIMER_MAX_ACTIVE = s.TIMER_MAX_ACTIVE
    _memory = s._memory
    _allocate_timer_id = s._allocate_timer_id
    _audit = s._audit
    _format_duration = s._format_duration

    start_time = time.monotonic()
    if not _tool_permitted("timer_create"):
        record_summary("timer_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    duration = _duration_seconds(args.get("duration"))
    if duration is None:
        _record_service_error("timer_create", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Duration is required and must be a positive value like 90, 90s, 5m, or 1h 30m.",
                }
            ]
        }
    _prune_timers()
    if len(_timers) >= TIMER_MAX_ACTIVE:
        _record_service_error("timer_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Too many active timers ({TIMER_MAX_ACTIVE} max)."}]}
    label = str(args.get("label", "")).strip()
    now_wall = time.time()
    now_mono = time.monotonic()
    due_wall = now_wall + duration
    due_mono = now_mono + duration
    timer_id: int
    if _memory is not None:
        try:
            timer_id = _memory.add_timer(
                due_at=due_wall,
                duration_sec=duration,
                label=label,
                created_at=now_wall,
            )
        except Exception:
            _record_service_error("timer_create", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Timer create failed: persistent storage unavailable."}]}
    else:
        timer_id = _allocate_timer_id()
    _timers[timer_id] = {
        "id": timer_id,
        "label": label,
        "duration_sec": duration,
        "created_at": now_wall,
        "due_at": due_wall,
        "due_mono": due_mono,
    }
    record_summary("timer_create", "ok", start_time, effect=f"timer_id={timer_id}", risk="low")
    _audit(
        "timer_create",
        {
            "result": "ok",
            "timer_id": timer_id,
            "duration_sec": duration,
            "label": label,
        },
    )
    due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_wall))
    label_text = f" '{label}'" if label else ""
    return {
        "content": [
            {
                "type": "text",
                "text": f"Timer {timer_id}{label_text} set for {_format_duration(duration)} (due at {due_local}).",
            }
        ]
    }
