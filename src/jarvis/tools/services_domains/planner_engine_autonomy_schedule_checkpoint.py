"""Autonomy schedule/checkpoint handlers for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _normalize_plan_steps(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    steps: list[str] = []
    seen: set[str] = set()
    for row in raw[:100]:
        text = ""
        if isinstance(row, str):
            text = row.strip()
        elif isinstance(row, dict):
            text = str(
                row.get("task")
                or row.get("step")
                or row.get("action")
                or row.get("title")
                or ""
            ).strip()
        if not text:
            continue
        signature = text.lower()
        if signature in seen:
            continue
        seen.add(signature)
        steps.append(text)
    return steps


def _normalize_condition_spec(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    source = str(raw.get("source", "runtime")).strip().lower() or "runtime"
    if source not in {"runtime", "payload", "task"}:
        source = "runtime"
    path = str(raw.get("path", "")).strip().strip(".")
    if not path:
        return {}
    condition: dict[str, Any] = {
        "source": source,
        "path": path,
    }
    if "equals" in raw:
        condition["equals"] = raw.get("equals")
    if isinstance(raw.get("in"), list):
        condition["in"] = list(raw.get("in", []))[:50]
    if "exists" in raw:
        condition["exists"] = bool(raw.get("exists"))
    if "gte" in raw:
        condition["gte"] = raw.get("gte")
    if "lte" in raw:
        condition["lte"] = raw.get("lte")
    return condition


def _normalize_step_contracts(raw: Any, *, step_count: int) -> list[dict[str, Any]]:
    if step_count <= 0:
        return []
    contracts: list[dict[str, Any]] = [{} for _ in range(step_count)]
    if not isinstance(raw, list):
        return contracts
    for idx, row in enumerate(raw[:step_count]):
        if not isinstance(row, dict):
            continue
        precondition = _normalize_condition_spec(row.get("precondition"))
        postcondition = _normalize_condition_spec(row.get("postcondition"))
        normalized: dict[str, Any] = {}
        if precondition:
            normalized["precondition"] = precondition
        if postcondition:
            normalized["postcondition"] = postcondition
        note = str(row.get("note", "")).strip()
        if note:
            normalized["note"] = note[:200]
        contracts[idx] = normalized
    return contracts


async def planner_autonomy_schedule(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _as_int = s._as_int
    _as_bool = s._as_bool
    _expansion_payload_response = s._expansion_payload_response
    _deferred_actions = s._deferred_actions
    _slugify_identifier = s._slugify_identifier
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_tasks = s._autonomy_tasks
    _goal_stack = s._goal_stack
    DEFERRED_ACTION_MAX = s.DEFERRED_ACTION_MAX
    GOAL_STACK_MAX = s.GOAL_STACK_MAX

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
    plan_steps = _normalize_plan_steps(
        args.get("plan_steps")
        if isinstance(args.get("plan_steps"), list)
        else payload_data.get("plan_steps")
        if isinstance(payload_data.get("plan_steps"), list)
        else args.get("steps")
    )
    step_cadence_sec = _as_float(
        args.get("step_cadence_sec", 300.0),
        300.0,
        minimum=0.0,
        maximum=86_400.0 * 7.0,
    )
    step_contracts = _normalize_step_contracts(
        args.get("step_contracts")
        if isinstance(args.get("step_contracts"), list)
        else payload_data.get("step_contracts")
        if isinstance(payload_data.get("step_contracts"), list)
        else [],
        step_count=len(plan_steps),
    )
    max_step_retries = _as_int(args.get("max_step_retries", 1), 1, minimum=0, maximum=5)
    retry_backoff_sec = _as_float(
        args.get("retry_backoff_sec", 15.0),
        15.0,
        minimum=0.0,
        maximum=86_400.0,
    )
    goal_title = str(args.get("goal", "")).strip()
    goal_id = _slugify_identifier(
        str(args.get("goal_id", "")).strip() or goal_title,
        fallback="",
    )
    if goal_id:
        exists = False
        for row in _goal_stack:
            if not isinstance(row, dict):
                continue
            if str(row.get("goal_id", "")).strip() == goal_id:
                row["updated_at"] = now
                if goal_title:
                    row["title"] = goal_title
                exists = True
                break
        if not exists:
            _goal_stack.append(
                {
                    "goal_id": goal_id,
                    "title": goal_title or title,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if len(_goal_stack) > GOAL_STACK_MAX:
                del _goal_stack[: len(_goal_stack) - GOAL_STACK_MAX]
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
        "plan_steps": plan_steps,
        "step_contracts": step_contracts,
        "plan_total_steps": len(plan_steps),
        "plan_step_index": 0,
        "plan_completed_steps": [],
        "plan_failed_steps": [],
        "plan_step_attempts": {},
        "step_cadence_sec": step_cadence_sec,
        "max_step_retries": max_step_retries,
        "retry_backoff_sec": retry_backoff_sec,
        "failure_taxonomy": {},
        "last_failure_reason": "",
        "needs_replan": False,
        "progress_pct": 0.0,
        "last_step_at": 0.0,
        "goal_id": goal_id,
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
        "goal_stack_depth": len(_goal_stack),
        "goal_id": goal_id,
        "plan_step_count": len(plan_steps),
        "step_contract_count": len([item for item in step_contracts if isinstance(item, dict) and item]),
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


async def planner_autonomy_replan(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _as_bool = s._as_bool
    _expansion_payload_response = s._expansion_payload_response
    _autonomy_tasks = s._autonomy_tasks
    _autonomy_replan_drafts = s._autonomy_replan_drafts

    task_id = str(args.get("task_id", "")).strip()
    if not task_id:
        _record_service_error("planner_engine", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "task_id is required."}]}

    row: dict[str, Any] | None = None
    for item in _autonomy_tasks():
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")) == task_id:
            row = item
            break
    if row is None:
        _record_service_error("planner_engine", start_time, "not_found")
        return {"content": [{"type": "text", "text": f"autonomy task not found: {task_id}"}]}

    payload_data = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    draft_id = str(args.get("draft_id", "")).strip().lower()
    draft_entry = (
        _autonomy_replan_drafts.get(draft_id)
        if draft_id and isinstance(_autonomy_replan_drafts.get(draft_id), dict)
        else None
    )
    if isinstance(draft_entry, dict):
        draft_task_id = str(draft_entry.get("task_id", "")).strip()
        if draft_task_id and draft_task_id != task_id:
            _record_service_error("planner_engine", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": f"draft_id does not match task_id: {draft_id}"}]}
    replan_steps = _normalize_plan_steps(
        args.get("plan_steps")
        if isinstance(args.get("plan_steps"), list)
        else draft_entry.get("plan_steps")
        if isinstance(draft_entry, dict) and isinstance(draft_entry.get("plan_steps"), list)
        else args.get("steps")
        if isinstance(args.get("steps"), list)
        else payload_data.get("plan_steps")
        if isinstance(payload_data.get("plan_steps"), list)
        else []
    )
    if replan_steps:
        row["plan_steps"] = replan_steps
        row["plan_total_steps"] = len(replan_steps)
    else:
        plan_steps_raw = row.get("plan_steps")
        existing_steps = (
            [str(item).strip() for item in plan_steps_raw if str(item).strip()]
            if isinstance(plan_steps_raw, list)
            else []
        )
        row["plan_steps"] = existing_steps
        row["plan_total_steps"] = len(existing_steps)

    step_contracts = _normalize_step_contracts(
        args.get("step_contracts")
        if isinstance(args.get("step_contracts"), list)
        else draft_entry.get("step_contracts")
        if isinstance(draft_entry, dict) and isinstance(draft_entry.get("step_contracts"), list)
        else payload_data.get("step_contracts")
        if isinstance(payload_data.get("step_contracts"), list)
        else [],
        step_count=int(row.get("plan_total_steps", 0) or 0),
    )
    if step_contracts:
        row["step_contracts"] = step_contracts
    elif not isinstance(row.get("step_contracts"), list):
        row["step_contracts"] = [{} for _ in range(int(row.get("plan_total_steps", 0) or 0))]

    reset_progress = _as_bool(args.get("reset_progress"), default=True)
    if reset_progress:
        row["plan_step_index"] = 0
        row["plan_completed_steps"] = []
        row["plan_failed_steps"] = []
        row["plan_step_attempts"] = {}
        row["progress_pct"] = 0.0

    now = time.time()
    execute_at = _as_float(args.get("execute_at", now), now, minimum=0.0)
    row["status"] = "scheduled"
    row["execute_at"] = execute_at
    row["needs_replan"] = False
    row["last_failure_reason"] = ""
    row["replan_count"] = int(row.get("replan_count", 0) or 0) + 1
    row["last_replan_at"] = now
    resolver_id = str(args.get("resolver_id", "")).strip().lower()
    if resolver_id:
        row["last_replan_by"] = resolver_id
    notes = str(args.get("notes", "")).strip()
    if notes:
        row["last_replan_notes"] = notes[:240]
    superseded_count = 0
    if isinstance(draft_entry, dict):
        draft_entry["status"] = "applied"
        draft_entry["applied_at"] = now
        draft_entry["applied_by"] = resolver_id or "operator"
        row["last_replan_draft_id"] = draft_id
    for candidate in _autonomy_replan_drafts.values():
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("task_id", "")).strip() != task_id:
            continue
        candidate_id = str(candidate.get("draft_id", "")).strip().lower()
        if draft_id and candidate_id == draft_id:
            continue
        if str(candidate.get("status", "pending")).strip().lower() != "pending":
            continue
        candidate["status"] = "superseded"
        candidate["superseded_at"] = now
        candidate["superseded_by"] = resolver_id or "operator"
        superseded_count += 1

    payload = {
        "action": "autonomy_replan",
        "task_id": task_id,
        "task": {
            "id": str(row.get("id", "")),
            "status": str(row.get("status", "")),
            "plan_step_index": int(row.get("plan_step_index", 0) or 0),
            "plan_total_steps": int(row.get("plan_total_steps", 0) or 0),
            "needs_replan": bool(row.get("needs_replan", False)),
            "replan_count": int(row.get("replan_count", 0) or 0),
            "execute_at": float(row.get("execute_at", 0.0) or 0.0),
        },
        "plan_step_count": int(row.get("plan_total_steps", 0) or 0),
        "step_contract_count": len(
            [
                item
                for item in (row.get("step_contracts") if isinstance(row.get("step_contracts"), list) else [])
                if isinstance(item, dict) and item
            ]
        ),
        "reset_progress": bool(reset_progress),
        "draft_id": draft_id,
        "superseded_draft_count": superseded_count,
    }
    record_summary("planner_engine", "ok", start_time, effect="autonomy_replan", risk="medium")
    return _expansion_payload_response(payload)


async def planner_autonomy_replan_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_int = s._as_int
    _expansion_payload_response = s._expansion_payload_response
    _autonomy_replan_drafts = s._autonomy_replan_drafts

    limit = _as_int(args.get("limit", 50), 50, minimum=1, maximum=500)
    task_id = str(args.get("task_id", "")).strip()
    status_filter = str(args.get("status_filter", "all")).strip().lower() or "all"
    if status_filter not in {"all", "pending", "applied", "superseded"}:
        status_filter = "all"
    rows = sorted(
        [
            row
            for row in _autonomy_replan_drafts.values()
            if isinstance(row, dict)
            and (not task_id or str(row.get("task_id", "")).strip() == task_id)
            and (status_filter == "all" or str(row.get("status", "")).strip().lower() == status_filter)
        ],
        key=lambda row: float(row.get("created_at", 0.0) or 0.0),
        reverse=True,
    )[:limit]
    payload = {
        "action": "autonomy_replan_list",
        "draft_count": len([row for row in _autonomy_replan_drafts.values() if isinstance(row, dict)]),
        "status_filter": status_filter,
        "task_id": task_id,
        "drafts": [dict(row) for row in rows],
    }
    record_summary("planner_engine", "ok", start_time, effect="autonomy_replan_list", risk="low")
    return _expansion_payload_response(payload)
