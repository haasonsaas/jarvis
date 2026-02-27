"""Planner domain service handlers extracted from services.py."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.planner_engine_autonomy import (
    planner_autonomy_checkpoint,
    planner_autonomy_cycle,
    planner_autonomy_schedule,
    planner_autonomy_status,
)
from jarvis.tools.services_domains.planner_engine_deferred import (
    planner_deferred_list,
    planner_deferred_schedule,
)
from jarvis.tools.services_domains.planner_engine_plan_graph import (
    planner_plan,
    planner_self_critique,
    planner_task_graph_create,
    planner_task_graph_resume,
    planner_task_graph_update,
)


def _services():
    from jarvis.tools import services as s

    return s


async def planner_engine(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("planner_engine"):
        record_summary("planner_engine", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "plan":
        return await planner_plan(args, start_time=start_time)
    if action == "task_graph_create":
        return await planner_task_graph_create(args, start_time=start_time)
    if action == "task_graph_update":
        return await planner_task_graph_update(args, start_time=start_time)
    if action == "task_graph_resume":
        return await planner_task_graph_resume(args, start_time=start_time)
    if action == "deferred_schedule":
        return await planner_deferred_schedule(args, start_time=start_time)
    if action == "deferred_list":
        return await planner_deferred_list(args, start_time=start_time)
    if action == "autonomy_schedule":
        return await planner_autonomy_schedule(args, start_time=start_time)
    if action == "autonomy_checkpoint":
        return await planner_autonomy_checkpoint(args, start_time=start_time)
    if action == "autonomy_cycle":
        return await planner_autonomy_cycle(args, start_time=start_time)
    if action == "autonomy_status":
        return await planner_autonomy_status(args, start_time=start_time)
    if action == "self_critique":
        return await planner_self_critique(args, start_time=start_time)

    _record_service_error("planner_engine", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown planner_engine action."}]}
