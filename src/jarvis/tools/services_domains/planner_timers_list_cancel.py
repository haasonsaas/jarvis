"""Timer list and cancel handlers."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def timer_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _as_bool = s._as_bool
    _prune_timers = s._prune_timers
    _timers = s._timers
    _format_duration = s._format_duration

    start_time = time.monotonic()
    if not _tool_permitted("timer_list"):
        record_summary("timer_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    include_expired = _as_bool(args.get("include_expired"), default=False)
    if not include_expired:
        _prune_timers()
    now = time.monotonic()
    rows = sorted(_timers.values(), key=lambda item: float(item.get("due_mono", now)))
    if not rows:
        record_summary("timer_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No active timers."}]}
    lines: list[str] = []
    for payload in rows:
        timer_id = int(payload.get("id", 0))
        label = str(payload.get("label", "")).strip()
        due_mono = float(payload.get("due_mono", now))
        due_wall = float(payload.get("due_at", time.time()))
        remaining = due_mono - now
        if remaining <= 0.0:
            if not include_expired:
                continue
            status = f"expired { _format_duration(abs(remaining)) } ago"
        else:
            status = f"due in {_format_duration(remaining)}"
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_wall))
        label_part = f" ({label})" if label else ""
        lines.append(f"- {timer_id}{label_part}: {status}; at {due_local}")
    if not lines:
        record_summary("timer_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No active timers."}]}
    record_summary("timer_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def timer_cancel(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _as_exact_int = s._as_exact_int
    _record_service_error = s._record_service_error
    _prune_timers = s._prune_timers
    _timers = s._timers
    _memory = s._memory
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("timer_cancel"):
        record_summary("timer_cancel", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    timer_id_raw = args.get("timer_id")
    label = str(args.get("label", "")).strip()
    parsed_timer_id = _as_exact_int(timer_id_raw) if timer_id_raw is not None else None
    if timer_id_raw is not None and (parsed_timer_id is None or parsed_timer_id <= 0):
        _record_service_error("timer_cancel", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "timer_id must be a positive integer."}]}
    if parsed_timer_id is None and not label:
        _record_service_error("timer_cancel", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Provide timer_id or label to cancel a timer."}]}
    _prune_timers()
    selected_id: int | None = None
    if parsed_timer_id is not None:
        if parsed_timer_id in _timers:
            selected_id = parsed_timer_id
    else:
        lowered = label.lower()
        for payload in sorted(_timers.values(), key=lambda item: float(item.get("due_mono", 0.0))):
            if str(payload.get("label", "")).strip().lower() == lowered:
                selected_id = int(payload.get("id", 0))
                break
    if selected_id is None:
        _record_service_error("timer_cancel", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Timer not found."}]}
    if _memory is not None:
        try:
            cancelled = _memory.cancel_timer(selected_id)
        except Exception:
            _record_service_error("timer_cancel", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Timer cancel failed: persistent storage unavailable."}]}
        if not cancelled:
            _record_service_error("timer_cancel", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Timer not found."}]}
    removed = _timers.pop(selected_id, None)
    if removed is None:
        _record_service_error("timer_cancel", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Timer not found."}]}
    record_summary("timer_cancel", "ok", start_time, effect=f"timer_id={selected_id}", risk="low")
    _audit(
        "timer_cancel",
        {
            "result": "ok",
            "timer_id": selected_id,
            "label": str(removed.get("label", "")),
        },
    )
    return {"content": [{"type": "text", "text": f"Cancelled timer {selected_id}."}]}
