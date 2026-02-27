"""Autonomy cycle handler for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def planner_autonomy_cycle(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _as_int = s._as_int
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response
    _slugify_identifier = s._slugify_identifier
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_tasks = s._autonomy_tasks
    _autonomy_cycle_history = s._autonomy_cycle_history
    _proactive_state = s._proactive_state
    AUTONOMY_CYCLE_HISTORY_MAX = s.AUTONOMY_CYCLE_HISTORY_MAX

    now = _as_float(args.get("now", time.time()), time.time(), minimum=0.0)
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    approved_checkpoints = set(_as_str_list(args.get("approved_checkpoints"), lower=True))
    due_rows = [
        row
        for row in _autonomy_tasks()
        if str(row.get("status", "")).strip().lower() in {"scheduled", "waiting_checkpoint"}
        and float(row.get("execute_at", now + 1.0)) <= now
    ]
    due_rows.sort(key=lambda row: float(row.get("execute_at", now)))
    due_rows = due_rows[:limit]
    executed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in due_rows:
        checkpoint_id = _slugify_identifier(str(row.get("checkpoint_id", "")).strip(), fallback="")
        requires_checkpoint = bool(row.get("requires_checkpoint", False))
        checkpoint_approved = bool(
            str(row.get("checkpoint_status", "")).strip().lower() == "approved"
            or (checkpoint_id and checkpoint_id in approved_checkpoints)
            or (
                checkpoint_id
                and bool(
                    isinstance(_autonomy_checkpoints.get(checkpoint_id), dict)
                    and _autonomy_checkpoints[checkpoint_id].get("approved")
                )
            )
        )
        if requires_checkpoint and not checkpoint_approved:
            row["status"] = "waiting_checkpoint"
            blocked.append(
                {
                    "id": str(row.get("id", "")),
                    "title": str(row.get("title", "")),
                    "checkpoint_id": checkpoint_id,
                    "reason": "checkpoint_required",
                }
            )
            continue
        if checkpoint_id:
            row["checkpoint_status"] = "approved"
            if checkpoint_id in _autonomy_checkpoints:
                _autonomy_checkpoints[checkpoint_id]["approved"] = True
                _autonomy_checkpoints[checkpoint_id]["updated_at"] = now
        row["last_executed_at"] = now
        row["run_count"] = int(row.get("run_count", 0) or 0) + 1
        recurrence_sec = _as_float(row.get("recurrence_sec", 0.0), 0.0, minimum=0.0)
        if recurrence_sec > 0.0:
            row["status"] = "scheduled"
            row["execute_at"] = now + recurrence_sec
        else:
            row["status"] = "completed"
        task_payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        task_text = str(task_payload.get("task") or task_payload.get("action") or row.get("title", "")).strip()
        if task_text:
            _proactive_state["pending_follow_through"].append(
                {
                    "created_at": now,
                    "task": task_text,
                    "payload": {str(k): v for k, v in task_payload.items()},
                }
            )
        executed.append(
            {
                "id": str(row.get("id", "")),
                "title": str(row.get("title", "")),
                "status": str(row.get("status", "")),
                "run_count": int(row.get("run_count", 0) or 0),
            }
        )
    cycle_summary = {
        "timestamp": now,
        "due_count": len(due_rows),
        "executed_count": len(executed),
        "blocked_count": len(blocked),
    }
    _autonomy_cycle_history.append(cycle_summary)
    if len(_autonomy_cycle_history) > AUTONOMY_CYCLE_HISTORY_MAX:
        del _autonomy_cycle_history[: len(_autonomy_cycle_history) - AUTONOMY_CYCLE_HISTORY_MAX]
    payload = {
        "action": "autonomy_cycle",
        "cycle": cycle_summary,
        "executed": executed,
        "blocked": blocked,
        "pending_follow_through_count": len(_proactive_state.get("pending_follow_through", [])),
    }
    record_summary("planner_engine", "ok", start_time, effect=f"autonomy_cycle:{len(executed)}", risk="medium" if blocked else "low")
    return _expansion_payload_response(payload)
