"""Home orchestration handlers."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.home_orch_automation import (
    home_orch_automation_apply,
    home_orch_automation_create,
    home_orch_automation_rollback,
    home_orch_automation_status,
    home_orch_automation_suggest,
)
from jarvis.tools.services_domains.home_orch_plan_exec import (
    home_orch_approval_list,
    home_orch_approval_resolve,
    home_orch_area_policy_list,
    home_orch_area_policy_set,
    home_orch_execute,
    home_orch_plan,
)
from jarvis.tools.services_domains.home_orch_tasks import (
    home_orch_task_list,
    home_orch_task_start,
    home_orch_task_update,
)


def _services():
    from jarvis.tools import services as s

    return s


async def home_orchestrator(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("home_orchestrator"):
        record_summary("home_orchestrator", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "plan":
        return await home_orch_plan(args, start_time=start_time)
    if action == "execute":
        return await home_orch_execute(args, start_time=start_time)
    if action == "approval_list":
        return await home_orch_approval_list(args, start_time=start_time)
    if action == "approval_resolve":
        return await home_orch_approval_resolve(args, start_time=start_time)
    if action == "area_policy_set":
        return await home_orch_area_policy_set(args, start_time=start_time)
    if action == "area_policy_list":
        return await home_orch_area_policy_list(args, start_time=start_time)
    if action == "automation_suggest":
        return await home_orch_automation_suggest(args, start_time=start_time)
    if action == "automation_create":
        return await home_orch_automation_create(args, start_time=start_time)
    if action == "automation_apply":
        return await home_orch_automation_apply(args, start_time=start_time)
    if action == "automation_rollback":
        return await home_orch_automation_rollback(args, start_time=start_time)
    if action == "automation_status":
        return await home_orch_automation_status(args, start_time=start_time)
    if action == "task_start":
        return await home_orch_task_start(args, start_time=start_time)
    if action == "task_update":
        return await home_orch_task_update(args, start_time=start_time)
    if action == "task_list":
        return await home_orch_task_list(args, start_time=start_time)

    _record_service_error("home_orchestrator", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown home_orchestrator action."}]}
