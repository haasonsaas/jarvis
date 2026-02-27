"""Autonomy handlers for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def planner_autonomy_schedule(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _as_bool = s._as_bool
    _expansion_payload_response = s._expansion_payload_response
    _deferred_actions = s._deferred_actions
    _slugify_identifier = s._slugify_identifier
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_tasks = s._autonomy_tasks
    DEFERRED_ACTION_MAX = s.DEFERRED_ACTION_MAX

    title = str(args.get("title", "autonomy-task")).strip() or "autonomy-task"
    risk = str(args.get("risk", "medium")).strip().lower() or "medium"
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    now = time.time()
    execute_at = _as_float(args.get("execute_at", now + 300.0), now + 300.0, minimum=0.0)
    recurrence_sec = _as_float(args.get("recurrence_sec", 0.0), 0.0, minimum=0.0, maximum=86_400.0 * 30.0)
    requires_checkpoint = _as_bool(args.get("requires_checkpoint"), default=(risk in {"medium", "high"}))
    checkpoint_id = _slugify_identifier(
        str(args.get("checkpoint_id", "")).strip() or f"checkpoint-{s._deferred_action_seq}",
        fallback=f"checkpoint-{s._deferred_action_seq}",
    )
    approved = _as_bool(args.get("approved"), default=False)
    action_id = f"deferred-{s._deferred_action_seq}"
    s._deferred_action_seq += 1
    payload_data = args.get("payload") if isinstance(args.get("payload"), dict) else {}
    entry = {
        "id": action_id,
        "title": title,
        "execute_at": execute_at,
        "payload": payload_data,
        "status": "scheduled",
        "created_at": now,
        "kind": "autonomy_task",
        "risk": risk,
        "requires_checkpoint": requires_checkpoint,
        "checkpoint_id": checkpoint_id,
        "checkpoint_status": "approved" if approved else "pending",
        "recurrence_sec": recurrence_sec,
        "run_count": 0,
    }
    _deferred_actions[action_id] = entry
    _autonomy_checkpoints.setdefault(
        checkpoint_id,
        {
            "checkpoint_id": checkpoint_id,
            "approved": approved,
            "updated_at": now,
            "notes": "",
        },
    )
    if len(_deferred_actions) > DEFERRED_ACTION_MAX:
        oldest = sorted(
            _deferred_actions.items(),
            key=lambda pair: float(pair[1].get("created_at", 0.0)),
        )[: len(_deferred_actions) - DEFERRED_ACTION_MAX]
        for key, _ in oldest:
            _deferred_actions.pop(key, None)
    row = {
        "action": "autonomy_schedule",
        "scheduled": dict(entry),
        "autonomy_task_count": len(_autonomy_tasks()),
    }
    record_summary("planner_engine", "ok", start_time, effect="autonomy_schedule", risk="medium" if requires_checkpoint else "low")
    return _expansion_payload_response(row)


async def planner_autonomy_checkpoint(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _expansion_payload_response = s._expansion_payload_response
    _slugify_identifier = s._slugify_identifier
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_tasks = s._autonomy_tasks

    checkpoint_id = _slugify_identifier(str(args.get("checkpoint_id", "")).strip(), fallback="")
    if not checkpoint_id:
        _record_service_error("planner_engine", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "checkpoint_id is required."}]}
    approved = _as_bool(args.get("approved"), default=False)
    notes = str(args.get("notes", "")).strip()
    now = time.time()
    _autonomy_checkpoints[checkpoint_id] = {
        "checkpoint_id": checkpoint_id,
        "approved": approved,
        "updated_at": now,
        "notes": notes,
    }
    affected = 0
    for row in _autonomy_tasks():
        if str(row.get("checkpoint_id", "")) != checkpoint_id:
            continue
        row["checkpoint_status"] = "approved" if approved else "pending"
        if approved and str(row.get("status", "")).strip().lower() == "waiting_checkpoint":
            row["status"] = "scheduled"
        affected += 1
    payload = {
        "action": "autonomy_checkpoint",
        "checkpoint": dict(_autonomy_checkpoints[checkpoint_id]),
        "affected_task_count": affected,
    }
    record_summary("planner_engine", "ok", start_time, effect="autonomy_checkpoint", risk="low")
    return _expansion_payload_response(payload)


async def planner_autonomy_cycle(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _as_int = s._as_int
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response
    _slugify_identifier = s._slugify_identifier
    _deferred_actions = s._deferred_actions
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


async def planner_autonomy_status(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
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
        (float(row.get("execute_at", 0.0) or 0.0) for row in rows if str(row.get("status", "")).strip().lower() in {"scheduled", "waiting_checkpoint"}),
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
