"""Planner domain service handlers extracted from services.py."""

from __future__ import annotations

import time
from typing import Any


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
