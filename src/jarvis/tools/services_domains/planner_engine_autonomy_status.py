"""Autonomy status handler for planner engine."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def planner_autonomy_status(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _autonomy_tasks = s._autonomy_tasks
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_cycle_history = s._autonomy_cycle_history

    rows = _autonomy_tasks()
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "scheduled")).strip().lower() or "scheduled"
        status_counts[status] = status_counts.get(status, 0) + 1
    next_due_at = min(
        (
            float(row.get("execute_at", 0.0) or 0.0)
            for row in rows
            if str(row.get("status", "")).strip().lower() in {"scheduled", "waiting_checkpoint"}
        ),
        default=0.0,
    )
    payload = {
        "action": "autonomy_status",
        "autonomy_task_count": len(rows),
        "status_counts": status_counts,
        "next_due_at": next_due_at,
        "checkpoints": {key: dict(value) for key, value in sorted(_autonomy_checkpoints.items())[:100]},
        "last_cycle": dict(_autonomy_cycle_history[-1]) if _autonomy_cycle_history else {},
    }
    record_summary("planner_engine", "ok", start_time, effect="autonomy_status", risk="low")
    return _expansion_payload_response(payload)
