"""Task plan create action handler."""

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
