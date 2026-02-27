"""Autonomy schedule/checkpoint handlers for planner engine."""

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
