"""Autonomy status handler for planner engine."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


async def planner_autonomy_status(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _autonomy_tasks = s._autonomy_tasks
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_cycle_history = s._autonomy_cycle_history
    _autonomy_replan_drafts = s._autonomy_replan_drafts
    _goal_stack = s._goal_stack
    _world_model_state = s._world_model_state
    _autonomy_slo_state = s._autonomy_slo_state

    rows = _autonomy_tasks()
    status_counts: dict[str, int] = {}
    failure_taxonomy: dict[str, int] = {}
    backlog_step_count = 0
    in_progress_count = 0
    needs_replan_count = 0
    retry_pending_count = 0
    task_progress: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("status", "scheduled")).strip().lower() or "scheduled"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "needs_replan":
            needs_replan_count += 1
        total_steps = _safe_int(row.get("plan_total_steps", 0) or 0)
        step_index = _safe_int(row.get("plan_step_index", 0) or 0)
        step_attempts = (
            {str(key): _safe_int(value or 0) for key, value in row.get("plan_step_attempts", {}).items()}
            if isinstance(row.get("plan_step_attempts"), dict)
            else {}
        )
        if step_attempts:
            retry_pending_count += 1
        if total_steps > 0:
            backlog_step_count += max(0, total_steps - max(0, step_index))
            if status in {"scheduled", "waiting_checkpoint"} and step_index > 0:
                in_progress_count += 1
        if isinstance(row.get("failure_taxonomy"), dict):
            for key, value in row.get("failure_taxonomy", {}).items():
                reason = str(key).strip().lower()
                if not reason:
                    continue
                failure_taxonomy[reason] = failure_taxonomy.get(reason, 0) + _safe_int(value or 0)
        task_progress.append(
            {
                "id": str(row.get("id", "")),
                "status": status,
                "plan_step_index": max(0, step_index),
                "plan_total_steps": max(0, total_steps),
                "progress_pct": float(row.get("progress_pct", 0.0) or 0.0),
                "retry_attempts": step_attempts,
                "last_failure_reason": str(row.get("last_failure_reason", "")),
                "needs_replan": bool(row.get("needs_replan", False)),
                "latest_replan_draft_id": str(row.get("latest_replan_draft_id", "")),
            }
        )
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
        "in_progress_count": in_progress_count,
        "needs_replan_count": needs_replan_count,
        "retry_pending_count": retry_pending_count,
        "backlog_step_count": backlog_step_count,
        "failure_taxonomy": failure_taxonomy,
        "task_progress": task_progress[:100],
        "checkpoints": {key: dict(value) for key, value in sorted(_autonomy_checkpoints.items())[:100]},
        "last_cycle": dict(_autonomy_cycle_history[-1]) if _autonomy_cycle_history else {},
        "replan_draft_count": len(_autonomy_replan_drafts),
        "replan_drafts": [
            dict(row)
            for row in sorted(
                [row for row in _autonomy_replan_drafts.values() if isinstance(row, dict)],
                key=lambda row: float(row.get("created_at", 0.0) or 0.0),
                reverse=True,
            )[:100]
        ],
        "goal_stack_depth": len(_goal_stack),
        "goals": [dict(row) for row in _goal_stack[:100] if isinstance(row, dict)],
        "world_model": {
            "entity_count": (
                len(_world_model_state.get("entities", {}))
                if isinstance(_world_model_state.get("entities"), dict)
                else 0
            ),
            "event_count": (
                len(_world_model_state.get("events", []))
                if isinstance(_world_model_state.get("events"), list)
                else 0
            ),
            "updated_at": float(_world_model_state.get("updated_at", 0.0) or 0.0),
        },
        "slo": (
            {
                "updated_at": float(_autonomy_slo_state.get("updated_at", 0.0) or 0.0),
                "metrics": (
                    {
                        str(key): value
                        for key, value in _autonomy_slo_state.get("metrics", {}).items()
                    }
                    if isinstance(_autonomy_slo_state.get("metrics"), dict)
                    else {}
                ),
                "alerts": (
                    [dict(row) for row in _autonomy_slo_state.get("alerts", []) if isinstance(row, dict)][:100]
                    if isinstance(_autonomy_slo_state.get("alerts"), list)
                    else []
                ),
            }
        ),
    }
    record_summary("planner_engine", "ok", start_time, effect="autonomy_status", risk="low")
    return _expansion_payload_response(payload)
