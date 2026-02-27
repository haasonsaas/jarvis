"""Plan/graph/self-critique handlers for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def planner_plan(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _as_str_list = s._as_str_list

    goal = str(args.get("goal", "")).strip()
    if not goal:
        _record_service_error("planner_engine", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "goal is required."}]}
    steps = _as_str_list(args.get("steps"))
    if not steps:
        steps = ["Clarify constraints", "Execute tool actions", "Verify outcomes", "Report completion"]
    payload = {
        "action": "plan",
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


async def planner_task_graph_create(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _as_str_list = s._as_str_list
    _planner_task_graphs = s._planner_task_graphs
    _planner_ready_nodes = s._planner_ready_nodes
    PLANNER_TASK_GRAPH_MAX = s.PLANNER_TASK_GRAPH_MAX

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
        "action": "task_graph_create",
        "graph_id": graph_id,
        "node_count": len(nodes),
        "ready_nodes": _planner_ready_nodes(graph),
    }
    record_summary("planner_engine", "ok", start_time, effect="graph_created", risk="low")
    return _expansion_payload_response(payload)


async def planner_task_graph_update(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _planner_task_graphs = s._planner_task_graphs
    _planner_ready_nodes = s._planner_ready_nodes

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
        "action": "task_graph_update",
        "graph_id": graph_id,
        "updated": True,
        "ready_nodes": _planner_ready_nodes(graph),
    }
    record_summary("planner_engine", "ok", start_time, effect="graph_updated", risk="low")
    return _expansion_payload_response(payload)


async def planner_task_graph_resume(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _planner_task_graphs = s._planner_task_graphs
    _planner_ready_nodes = s._planner_ready_nodes

    graph_id = str(args.get("graph_id", "")).strip()
    if graph_id:
        graph = _planner_task_graphs.get(graph_id)
        if not isinstance(graph, dict):
            _record_service_error("planner_engine", start_time, "not_found")
            return {"content": [{"type": "text", "text": "graph_id not found."}]}
        payload = {
            "action": "task_graph_resume",
            "graph_id": graph_id,
            "ready_nodes": _planner_ready_nodes(graph),
        }
    else:
        payload = {
            "action": "task_graph_resume",
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


async def planner_self_critique(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response

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
        "action": "self_critique",
        "complexity": complexity,
        "step_count": step_count,
        "warnings": warnings,
        "recommendation": "approve" if not warnings else "revise",
    }
    record_summary("planner_engine", "ok", start_time, effect=f"critique:{payload['recommendation']}", risk="low")
    return _expansion_payload_response(payload)
