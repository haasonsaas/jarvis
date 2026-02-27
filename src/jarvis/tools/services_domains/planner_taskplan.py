"""Task-plan persistence handlers."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

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
