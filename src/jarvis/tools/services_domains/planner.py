"""Planner domain service handlers extracted from services.py."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.planner_runtime import (
    due_unnotified_reminder_payloads as _runtime_due_unnotified_reminder_payloads,
    list_reminder_payloads as _runtime_list_reminder_payloads,
)


def _services():
    from jarvis.tools import services as s

    return s


async def planner_engine(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _as_int = s._as_int
    _as_float = s._as_float
    _as_bool = s._as_bool
    _as_str_list = s._as_str_list
    _planner_task_graphs = s._planner_task_graphs
    _planner_ready_nodes = s._planner_ready_nodes
    _deferred_actions = s._deferred_actions
    _slugify_identifier = s._slugify_identifier
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_tasks = s._autonomy_tasks
    _autonomy_cycle_history = s._autonomy_cycle_history
    _proactive_state = s._proactive_state
    PLANNER_TASK_GRAPH_MAX = s.PLANNER_TASK_GRAPH_MAX
    DEFERRED_ACTION_MAX = s.DEFERRED_ACTION_MAX
    AUTONOMY_CYCLE_HISTORY_MAX = s.AUTONOMY_CYCLE_HISTORY_MAX

    start_time = time.monotonic()
    if not _tool_permitted("planner_engine"):
        record_summary("planner_engine", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "plan":
        goal = str(args.get("goal", "")).strip()
        if not goal:
            _record_service_error("planner_engine", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "goal is required."}]}
        steps = _as_str_list(args.get("steps"))
        if not steps:
            steps = ["Clarify constraints", "Execute tool actions", "Verify outcomes", "Report completion"]
        payload = {
            "action": action,
            "goal": goal,
            "planner": {
                "steps": steps,
                "retry_policy": "retry_failed_steps_once_then_escalate",
                "rollback_hints": [
                    "Store pre-change state when possible.",
                    "Use dry-run for medium/high-risk actions first.",
                ],
            },
            "executor": {
                "mode": "deterministic",
                "checkpointing": True,
                "max_retries_per_step": 1,
            },
        }
        record_summary("planner_engine", "ok", start_time, effect="plan_generated", risk="low")
        return _expansion_payload_response(payload)

    if action == "task_graph_create":
        title = str(args.get("title", "Task Graph")).strip() or "Task Graph"
        steps = args.get("steps") if isinstance(args.get("steps"), list) else []
        nodes: list[dict[str, Any]] = []
        for idx, row in enumerate(steps):
            if isinstance(row, dict):
                node_id = str(row.get("id", f"n{idx+1}")).strip() or f"n{idx+1}"
                text = str(row.get("text", f"Step {idx+1}")).strip() or f"Step {idx+1}"
                deps = _as_str_list(row.get("depends_on"), lower=False)
            else:
                node_id = f"n{idx+1}"
                text = str(row).strip() or f"Step {idx+1}"
                deps = []
            nodes.append({"id": node_id, "text": text, "depends_on": deps, "status": "pending"})
        if not nodes:
            nodes = [{"id": "n1", "text": "Execute goal", "depends_on": [], "status": "pending"}]
        graph_id = f"graph-{s._planner_task_seq}"
        s._planner_task_seq += 1
        graph = {
            "graph_id": graph_id,
            "title": title,
            "nodes": nodes,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        _planner_task_graphs[graph_id] = graph
        if len(_planner_task_graphs) > PLANNER_TASK_GRAPH_MAX:
            oldest = sorted(
                _planner_task_graphs.items(),
                key=lambda pair: float(pair[1].get("updated_at", 0.0)),
            )[: len(_planner_task_graphs) - PLANNER_TASK_GRAPH_MAX]
            for key, _ in oldest:
                _planner_task_graphs.pop(key, None)
        payload = {
            "action": action,
            "graph_id": graph_id,
            "node_count": len(nodes),
            "ready_nodes": _planner_ready_nodes(graph),
        }
        record_summary("planner_engine", "ok", start_time, effect="graph_created", risk="low")
        return _expansion_payload_response(payload)

    if action == "task_graph_update":
        graph_id = str(args.get("graph_id", "")).strip()
        node_id = str(args.get("node_id", "")).strip()
        status = str(args.get("status", "pending")).strip().lower()
        if status not in {"pending", "in_progress", "blocked", "done"}:
            _record_service_error("planner_engine", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "status must be pending|in_progress|blocked|done."}]}
        graph = _planner_task_graphs.get(graph_id)
        if not isinstance(graph, dict):
            _record_service_error("planner_engine", start_time, "not_found")
            return {"content": [{"type": "text", "text": "graph_id not found."}]}
        updated = False
        for node in graph.get("nodes", []):
            if isinstance(node, dict) and str(node.get("id", "")) == node_id:
                node["status"] = status
                updated = True
                break
        if not updated:
            _record_service_error("planner_engine", start_time, "not_found")
            return {"content": [{"type": "text", "text": "node_id not found."}]}
        graph["updated_at"] = time.time()
        payload = {
            "action": action,
            "graph_id": graph_id,
            "updated": True,
            "ready_nodes": _planner_ready_nodes(graph),
        }
        record_summary("planner_engine", "ok", start_time, effect="graph_updated", risk="low")
        return _expansion_payload_response(payload)

    if action == "task_graph_resume":
        graph_id = str(args.get("graph_id", "")).strip()
        if graph_id:
            graph = _planner_task_graphs.get(graph_id)
            if not isinstance(graph, dict):
                _record_service_error("planner_engine", start_time, "not_found")
                return {"content": [{"type": "text", "text": "graph_id not found."}]}
            payload = {
                "action": action,
                "graph_id": graph_id,
                "ready_nodes": _planner_ready_nodes(graph),
            }
        else:
            payload = {
                "action": action,
                "graphs": [
                    {
                        "graph_id": key,
                        "ready_nodes": _planner_ready_nodes(row),
                    }
                    for key, row in sorted(_planner_task_graphs.items())
                ],
            }
        record_summary("planner_engine", "ok", start_time, effect="graph_resume", risk="low")
        return _expansion_payload_response(payload)

    if action == "deferred_schedule":
        title = str(args.get("title", "deferred-action")).strip() or "deferred-action"
        execute_at = _as_float(args.get("execute_at", time.time() + 60.0), time.time() + 60.0, minimum=0.0)
        action_id = f"deferred-{s._deferred_action_seq}"
        s._deferred_action_seq += 1
        _deferred_actions[action_id] = {
            "id": action_id,
            "title": title,
            "execute_at": execute_at,
            "payload": args.get("payload") if isinstance(args.get("payload"), dict) else {},
            "status": "scheduled",
            "created_at": time.time(),
        }
        if len(_deferred_actions) > DEFERRED_ACTION_MAX:
            oldest = sorted(_deferred_actions.items(), key=lambda pair: float(pair[1].get("created_at", 0.0)))[: len(_deferred_actions) - DEFERRED_ACTION_MAX]
            for key, _ in oldest:
                _deferred_actions.pop(key, None)
        payload = {"action": action, "scheduled": dict(_deferred_actions[action_id]), "deferred_count": len(_deferred_actions)}
        record_summary("planner_engine", "ok", start_time, effect="deferred_schedule", risk="low")
        return _expansion_payload_response(payload)

    if action == "deferred_list":
        limit = _as_int(args.get("limit", 50), 50, minimum=1, maximum=200)
        rows = sorted(_deferred_actions.values(), key=lambda item: float(item.get("execute_at", 0.0)))[:limit]
        payload = {"action": action, "deferred_count": len(_deferred_actions), "items": rows}
        record_summary("planner_engine", "ok", start_time, effect="deferred_list", risk="low")
        return _expansion_payload_response(payload)

    if action == "autonomy_schedule":
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
            "action": action,
            "scheduled": dict(entry),
            "autonomy_task_count": len(_autonomy_tasks()),
        }
        record_summary("planner_engine", "ok", start_time, effect="autonomy_schedule", risk="medium" if requires_checkpoint else "low")
        return _expansion_payload_response(row)

    if action == "autonomy_checkpoint":
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
            "action": action,
            "checkpoint": dict(_autonomy_checkpoints[checkpoint_id]),
            "affected_task_count": affected,
        }
        record_summary("planner_engine", "ok", start_time, effect="autonomy_checkpoint", risk="low")
        return _expansion_payload_response(payload)

    if action == "autonomy_cycle":
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
            "action": action,
            "cycle": cycle_summary,
            "executed": executed,
            "blocked": blocked,
            "pending_follow_through_count": len(_proactive_state.get("pending_follow_through", [])),
        }
        record_summary("planner_engine", "ok", start_time, effect=f"autonomy_cycle:{len(executed)}", risk="medium" if blocked else "low")
        return _expansion_payload_response(payload)

    if action == "autonomy_status":
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
            "action": action,
            "autonomy_task_count": len(rows),
            "status_counts": status_counts,
            "next_due_at": next_due_at,
            "checkpoints": {key: dict(value) for key, value in sorted(_autonomy_checkpoints.items())[:100]},
            "last_cycle": dict(_autonomy_cycle_history[-1]) if _autonomy_cycle_history else {},
        }
        record_summary("planner_engine", "ok", start_time, effect="autonomy_status", risk="low")
        return _expansion_payload_response(payload)

    if action == "self_critique":
        plan = args.get("plan") if isinstance(args.get("plan"), dict) else {}
        steps = plan.get("steps")
        step_count = len(steps) if isinstance(steps, list) else 0
        complexity = "high" if step_count >= 8 else "medium" if step_count >= 4 else "low"
        warnings: list[str] = []
        if step_count >= 8:
            warnings.append("Plan has many steps; consider decomposition.")
        if any("delete" in str(step).lower() for step in (steps or [])):
            warnings.append("Contains destructive operations; require confirmation checkpoints.")
        payload = {
            "action": action,
            "complexity": complexity,
            "step_count": step_count,
            "warnings": warnings,
            "recommendation": "approve" if not warnings else "revise",
        }
        record_summary("planner_engine", "ok", start_time, effect=f"critique:{payload['recommendation']}", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("planner_engine", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown planner_engine action."}]}


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


def _list_reminder_payloads(*, include_completed: bool, limit: int, now_ts: float) -> list[dict[str, Any]]:
    s = _services()
    return _runtime_list_reminder_payloads(
        memory=s._memory,
        reminders=s._reminders,
        include_completed=include_completed,
        limit=limit,
        now_ts=now_ts,
    )


def _due_unnotified_reminder_payloads(*, limit: int, now_ts: float) -> list[dict[str, Any]]:
    s = _services()
    return _runtime_due_unnotified_reminder_payloads(
        memory=s._memory,
        reminders=s._reminders,
        limit=limit,
        now_ts=now_ts,
    )


async def reminder_create(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _parse_due_timestamp = s._parse_due_timestamp
    _reminder_status = s._reminder_status
    REMINDER_MAX_ACTIVE = s.REMINDER_MAX_ACTIVE
    _memory = s._memory
    _allocate_reminder_id = s._allocate_reminder_id
    _reminders = s._reminders
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("reminder_create"):
        record_summary("reminder_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("reminder_create", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Reminder text is required."}]}
    now = time.time()
    due_at = _parse_due_timestamp(args.get("due"), now_ts=now)
    if due_at is None:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Reminder due value must be epoch seconds, ISO datetime, or a relative duration like 'in 20m'.",
                }
            ]
        }
    if due_at <= now:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Reminder due time must be in the future."}]}
    pending_count = int(_reminder_status().get("pending_count", 0))
    if pending_count >= REMINDER_MAX_ACTIVE:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Too many pending reminders ({REMINDER_MAX_ACTIVE} max)."}]}

    reminder_id: int
    if _memory is not None:
        try:
            reminder_id = _memory.add_reminder(text=text, due_at=due_at, created_at=now)
        except Exception:
            _record_service_error("reminder_create", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Reminder create failed: persistent storage unavailable."}]}
    else:
        reminder_id = _allocate_reminder_id()
    _reminders[reminder_id] = {
        "id": reminder_id,
        "text": text,
        "due_at": due_at,
        "created_at": now,
        "status": "pending",
        "completed_at": None,
        "notified_at": None,
    }
    due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_at))
    record_summary("reminder_create", "ok", start_time, effect=f"reminder_id={reminder_id}", risk="low")
    _audit(
        "reminder_create",
        {
            "result": "ok",
            "reminder_id": reminder_id,
            "text_length": len(text),
            "due_at": due_at,
        },
    )
    return {"content": [{"type": "text", "text": f"Reminder {reminder_id} set for {due_local}."}]}


async def reminder_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _as_bool = s._as_bool
    _as_int = s._as_int
    _record_service_error = s._record_service_error
    _format_duration = s._format_duration
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("reminder_list"):
        record_summary("reminder_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    include_completed = _as_bool(args.get("include_completed"), default=False)
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=100)
    now = time.time()
    try:
        payloads = _list_reminder_payloads(include_completed=include_completed, limit=limit, now_ts=now)
    except Exception:
        _record_service_error("reminder_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": "Reminder list failed: persistent storage unavailable."}]}
    if not payloads:
        record_summary("reminder_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No reminders found."}]}
    lines: list[str] = []
    for payload in payloads:
        reminder_id = int(payload.get("id", 0))
        text = str(payload.get("text", "")).strip() or "(untitled)"
        status = str(payload.get("status", "pending"))
        due_at = float(payload.get("due_at", now))
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_at))
        if status == "completed":
            completed_at = payload.get("completed_at")
            completed_local = (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(completed_at)))
                if completed_at is not None
                else "unknown"
            )
            lines.append(f"- {reminder_id}: {text} (completed at {completed_local}; due at {due_local})")
            continue
        remaining = due_at - now
        if remaining <= 0.0:
            when_text = f"overdue by {_format_duration(abs(remaining))}"
        else:
            when_text = f"due in {_format_duration(remaining)}"
        lines.append(f"- {reminder_id}: {text} ({when_text}; at {due_local})")
    record_summary("reminder_list", "ok", start_time)
    _audit(
        "reminder_list",
        {"result": "ok", "count": len(lines), "include_completed": include_completed},
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def reminder_complete(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _as_exact_int = s._as_exact_int
    _record_service_error = s._record_service_error
    _memory = s._memory
    _reminders = s._reminders
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("reminder_complete"):
        record_summary("reminder_complete", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    reminder_id = _as_exact_int(args.get("reminder_id"))
    if reminder_id is None or reminder_id <= 0:
        _record_service_error("reminder_complete", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "reminder_id must be a positive integer."}]}
    if _memory is not None:
        try:
            completed = _memory.complete_reminder(reminder_id)
        except Exception:
            _record_service_error("reminder_complete", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Reminder complete failed: persistent storage unavailable."}]}
        if not completed:
            _record_service_error("reminder_complete", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Reminder not found."}]}
    else:
        payload = _reminders.get(reminder_id)
        if payload is None or str(payload.get("status", "pending")) != "pending":
            _record_service_error("reminder_complete", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Reminder not found."}]}
        payload["status"] = "completed"
        payload["completed_at"] = time.time()
    if reminder_id in _reminders:
        _reminders[reminder_id]["status"] = "completed"
        _reminders[reminder_id]["completed_at"] = time.time()
    record_summary("reminder_complete", "ok", start_time, effect=f"reminder_id={reminder_id}", risk="low")
    _audit("reminder_complete", {"result": "ok", "reminder_id": reminder_id})
    return {"content": [{"type": "text", "text": f"Completed reminder {reminder_id}."}]}


async def reminder_notify_due(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _audit = s._audit
    _config = s._config
    _as_int = s._as_int
    _as_float = s._as_float
    _normalize_nudge_policy = s._normalize_nudge_policy
    _nudge_policy = s._nudge_policy
    _quiet_window_active = s._quiet_window_active
    pushover_notify = s.pushover_notify
    _memory = s._memory
    _reminders = s._reminders

    start_time = time.monotonic()
    if not _tool_permitted("reminder_notify_due"):
        record_summary("reminder_notify_due", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _tool_permitted("pushover_notify"):
        _record_service_error("reminder_notify_due", start_time, "policy")
        _audit("reminder_notify_due", {"result": "denied", "reason": "pushover_policy"})
        return {"content": [{"type": "text", "text": "Pushover notifications are disabled by policy."}]}
    if not _config or not str(_config.pushover_api_token).strip() or not str(_config.pushover_user_key).strip():
        _record_service_error("reminder_notify_due", start_time, "missing_config")
        _audit("reminder_notify_due", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    title = str(args.get("title", "Jarvis reminders")).strip() or "Jarvis reminders"
    now = time.time()
    try:
        due_payloads = _due_unnotified_reminder_payloads(limit=limit, now_ts=now)
    except Exception:
        _record_service_error("reminder_notify_due", start_time, "storage_error")
        return {
            "content": [
                {"type": "text", "text": "Reminder notification dispatch failed: persistent storage unavailable."}
            ]
        }
    if not due_payloads:
        record_summary("reminder_notify_due", "empty", start_time)
        _audit("reminder_notify_due", {"result": "empty", "limit": limit})
        return {"content": [{"type": "text", "text": "No due reminders awaiting notification."}]}

    policy = _normalize_nudge_policy(args.get("nudge_policy", _nudge_policy))
    quiet_active = _quiet_window_active(now_ts=now)
    deferred_count = 0
    dispatch_payloads = due_payloads
    if quiet_active and policy in {"defer", "adaptive"}:
        if policy == "defer":
            deferred_count = len(dispatch_payloads)
            dispatch_payloads = []
        else:
            urgent_overdue_sec = _as_float(
                args.get("urgent_overdue_sec", 3600.0),
                3600.0,
                minimum=60.0,
                maximum=86_400.0,
            )
            urgent_payloads: list[dict[str, Any]] = []
            for payload in dispatch_payloads:
                due_at = float(payload.get("due_at", now))
                overdue_sec = max(0.0, now - due_at)
                if overdue_sec >= urgent_overdue_sec:
                    urgent_payloads.append(payload)
            deferred_count = max(0, len(dispatch_payloads) - len(urgent_payloads))
            dispatch_payloads = urgent_payloads
    if not dispatch_payloads and deferred_count > 0:
        record_summary("reminder_notify_due", "deferred", start_time, effect=f"deferred={deferred_count}", risk="low")
        _audit(
            "reminder_notify_due",
            {
                "result": "deferred",
                "policy": policy,
                "quiet_window_active": quiet_active,
                "deferred_count": deferred_count,
                "limit": limit,
            },
        )
        return {"content": [{"type": "text", "text": f"Deferred {deferred_count} due reminder notifications until quiet hours end."}]}

    sent = 0
    failed = 0
    for payload in dispatch_payloads:
        reminder_id = int(payload.get("id", 0))
        text = str(payload.get("text", "")).strip() or "(untitled)"
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(payload.get("due_at", now))))
        notify_result = await pushover_notify(
            {"title": title, "priority": 0, "message": f"Reminder {reminder_id}: {text} (due {due_local})"}
        )
        notify_text = str(notify_result.get("content", [{}])[0].get("text", "")).strip().lower()
        if "notification sent" not in notify_text:
            failed += 1
            continue
        sent += 1
        if _memory is not None:
            try:
                _memory.mark_reminder_notified(reminder_id, notified_at=time.time())
            except Exception:
                failed += 1
                sent -= 1
                continue
        if reminder_id in _reminders:
            _reminders[reminder_id]["notified_at"] = time.time()
    if sent == 0 and failed > 0:
        _record_service_error("reminder_notify_due", start_time, "api_error")
        _audit(
            "reminder_notify_due",
            {
                "result": "api_error",
                "sent": sent,
                "failed": failed,
                "deferred_count": deferred_count,
                "policy": policy,
                "quiet_window_active": quiet_active,
            },
        )
        return {"content": [{"type": "text", "text": "Unable to send due reminder notifications."}]}
    record_summary("reminder_notify_due", "ok", start_time, effect=f"sent={sent}", risk="low")
    _audit(
        "reminder_notify_due",
        {
            "result": "ok",
            "sent": sent,
            "failed": failed,
            "deferred_count": deferred_count,
            "policy": policy,
            "quiet_window_active": quiet_active,
        },
    )
    suffix = f" ({failed} failed)." if failed else "."
    if deferred_count > 0:
        suffix += f" Deferred: {deferred_count}."
    return {"content": [{"type": "text", "text": f"Due reminder notifications sent: {sent}{suffix}"}]}


async def task_plan_create(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _memory = s._memory
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("task_plan_create"):
        record_summary("task_plan_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_create", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    title = str(args.get("title", "")).strip()
    steps = args.get("steps")
    if not title or not isinstance(steps, list) or not steps:
        _record_service_error("task_plan_create", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan title and steps required."}]}
    try:
        plan_id = _memory.add_task_plan(title, [str(step) for step in steps])
    except ValueError:
        _record_service_error("task_plan_create", start_time, "invalid_steps")
        return {"content": [{"type": "text", "text": "Plan requires at least one non-empty step."}]}
    except Exception as e:
        _record_service_error("task_plan_create", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan create failed: {e}"}]}
    record_summary("task_plan_create", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Plan created (id={plan_id})."}]}


async def task_plan_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool

    start_time = time.monotonic()
    if not _tool_permitted("task_plan_list"):
        record_summary("task_plan_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    open_only = _as_bool(args.get("open_only"), default=True)
    try:
        plans = _memory.list_task_plans(open_only=open_only)
    except Exception as e:
        _record_service_error("task_plan_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan list failed: {e}"}]}
    if not plans:
        record_summary("task_plan_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No task plans found."}]}
    blocks = []
    for plan in plans:
        header = f"Plan {plan.id}: {plan.title} ({plan.status})"
        steps = "\n".join([f"  {step.index + 1}. {step.text} [{step.status}]" for step in plan.steps])
        blocks.append(f"{header}\n{steps}")
    record_summary("task_plan_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}]}


async def task_plan_update(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int

    start_time = time.monotonic()
    if not _tool_permitted("task_plan_update"):
        record_summary("task_plan_update", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_update", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_exact_int(args.get("plan_id"))
    step_index = _as_exact_int(args.get("step_index"))
    status = str(args.get("status", "pending")).strip().lower()
    allowed_status = {"pending", "in_progress", "blocked", "done"}
    if plan_id is None or plan_id <= 0 or step_index is None or step_index < 0:
        _record_service_error("task_plan_update", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan id and step index required."}]}
    if status not in allowed_status:
        _record_service_error("task_plan_update", start_time, "invalid_status")
        return {"content": [{"type": "text", "text": "Status must be one of: pending, in_progress, blocked, done."}]}
    try:
        updated = _memory.update_task_step(plan_id, step_index, status)
    except Exception as e:
        _record_service_error("task_plan_update", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan update failed: {e}"}]}
    if not updated:
        record_summary("task_plan_update", "empty", start_time)
        return {"content": [{"type": "text", "text": "No task step updated."}]}
    record_summary("task_plan_update", "ok", start_time)
    return {"content": [{"type": "text", "text": "Plan updated."}]}


async def task_plan_summary(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int

    start_time = time.monotonic()
    if not _tool_permitted("task_plan_summary"):
        record_summary("task_plan_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_summary", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_exact_int(args.get("plan_id"))
    if plan_id is None or plan_id <= 0:
        _record_service_error("task_plan_summary", start_time, "missing_plan")
        return {"content": [{"type": "text", "text": "Plan id required."}]}
    try:
        progress = _memory.task_plan_progress(plan_id)
    except Exception as e:
        _record_service_error("task_plan_summary", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan summary failed: {e}"}]}
    if not progress:
        record_summary("task_plan_summary", "empty", start_time)
        return {"content": [{"type": "text", "text": "Plan not found."}]}
    done, total = progress
    text = f"Plan {plan_id}: {done}/{total} steps complete."
    record_summary("task_plan_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


async def task_plan_next(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int

    start_time = time.monotonic()
    if not _tool_permitted("task_plan_next"):
        record_summary("task_plan_next", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_next", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = args.get("plan_id")
    parsed_plan_id = _as_exact_int(plan_id) if plan_id is not None else None
    if plan_id is not None and (parsed_plan_id is None or parsed_plan_id <= 0):
        _record_service_error("task_plan_next", start_time, "invalid_plan")
        return {"content": [{"type": "text", "text": "Plan id must be a positive integer."}]}
    try:
        plan = _memory.next_task_step(parsed_plan_id) if parsed_plan_id else _memory.next_task_step()
    except Exception as e:
        _record_service_error("task_plan_next", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan next failed: {e}"}]}
    if not plan:
        record_summary("task_plan_next", "empty", start_time)
        return {"content": [{"type": "text", "text": "No pending steps found."}]}
    task_plan, step = plan
    text = f"Next step for plan {task_plan.id} ({task_plan.title}): {step.index + 1}. {step.text}"
    record_summary("task_plan_next", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}
