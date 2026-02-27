"""Task graph actions for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


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
