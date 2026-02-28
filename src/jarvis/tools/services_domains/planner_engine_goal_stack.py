"""Long-horizon goal stack handlers for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def planner_goal_push(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _slugify_identifier = s._slugify_identifier
    _expansion_payload_response = s._expansion_payload_response
    _goal_stack = s._goal_stack

    title = str(args.get("title", "")).strip()
    if not title:
        _record_service_error("planner_engine", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "title is required for goal_push."}]}

    goal_id = _slugify_identifier(str(args.get("goal_id", "")).strip() or title, fallback="goal")
    now = time.time()
    existing: dict[str, Any] | None = None
    for row in _goal_stack:
        if isinstance(row, dict) and str(row.get("goal_id", "")).strip() == goal_id:
            existing = row
            break
    if existing is None:
        existing = {
            "goal_id": goal_id,
            "title": title,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "priority": s._as_int(args.get("priority", 50), 50, minimum=0, maximum=100),
            "horizon": str(args.get("horizon", "long")).strip().lower() or "long",
            "notes": str(args.get("notes", "")).strip()[:240],
        }
        _goal_stack.append(existing)
        if len(_goal_stack) > s.GOAL_STACK_MAX:
            del _goal_stack[: len(_goal_stack) - s.GOAL_STACK_MAX]
        effect = "goal_push:new"
    else:
        existing["title"] = title
        existing["updated_at"] = now
        if "priority" in args:
            existing["priority"] = s._as_int(args.get("priority", 50), 50, minimum=0, maximum=100)
        if "status" in args:
            existing["status"] = str(args.get("status", "active")).strip().lower() or "active"
        if "notes" in args:
            existing["notes"] = str(args.get("notes", "")).strip()[:240]
        effect = "goal_push:update"

    payload = {
        "action": "goal_push",
        "goal": dict(existing),
        "goal_stack_depth": len(_goal_stack),
    }
    record_summary("planner_engine", "ok", start_time, effect=effect, risk="low")
    return _expansion_payload_response(payload)


async def planner_goal_pop(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _goal_stack = s._goal_stack

    goal_id = str(args.get("goal_id", "")).strip()
    removed: dict[str, Any] | None = None
    if goal_id:
        for index, row in enumerate(list(_goal_stack)):
            if isinstance(row, dict) and str(row.get("goal_id", "")).strip() == goal_id:
                removed = dict(row)
                _goal_stack.pop(index)
                break
    elif _goal_stack:
        row = _goal_stack.pop()
        removed = dict(row) if isinstance(row, dict) else None

    payload = {
        "action": "goal_pop",
        "removed": removed,
        "goal_stack_depth": len(_goal_stack),
    }
    record_summary("planner_engine", "ok", start_time, effect="goal_pop", risk="low")
    return _expansion_payload_response(payload)


async def planner_goal_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_int = s._as_int
    _expansion_payload_response = s._expansion_payload_response
    _goal_stack = s._goal_stack

    limit = _as_int(args.get("limit", 50), 50, minimum=1, maximum=500)
    status_filter = str(args.get("status_filter", "all")).strip().lower() or "all"
    rows = [row for row in _goal_stack if isinstance(row, dict)]
    if status_filter != "all":
        rows = [row for row in rows if str(row.get("status", "")).strip().lower() == status_filter]
    rows = sorted(
        rows,
        key=lambda row: (
            -s._as_int(row.get("priority", 50), 50, minimum=0, maximum=100),
            -s._as_float(row.get("updated_at", 0.0), 0.0, minimum=0.0),
        ),
    )[:limit]
    payload = {
        "action": "goal_list",
        "goal_stack_depth": len(_goal_stack),
        "status_filter": status_filter,
        "goals": [dict(row) for row in rows],
    }
    record_summary("planner_engine", "ok", start_time, effect="goal_list", risk="low")
    return _expansion_payload_response(payload)


async def planner_goal_update(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _goal_stack = s._goal_stack

    goal_id = str(args.get("goal_id", "")).strip()
    if not goal_id:
        _record_service_error("planner_engine", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "goal_id is required for goal_update."}]}

    target: dict[str, Any] | None = None
    for row in _goal_stack:
        if isinstance(row, dict) and str(row.get("goal_id", "")).strip() == goal_id:
            target = row
            break
    if target is None:
        _record_service_error("planner_engine", start_time, "not_found")
        return {"content": [{"type": "text", "text": f"goal not found: {goal_id}"}]}

    if "title" in args:
        target["title"] = str(args.get("title", "")).strip() or str(target.get("title", ""))
    if "status" in args:
        target["status"] = str(args.get("status", "active")).strip().lower() or "active"
    if "priority" in args:
        target["priority"] = s._as_int(args.get("priority", 50), 50, minimum=0, maximum=100)
    if "notes" in args:
        target["notes"] = str(args.get("notes", "")).strip()[:240]
    target["updated_at"] = time.time()

    payload = {
        "action": "goal_update",
        "goal": dict(target),
        "goal_stack_depth": len(_goal_stack),
    }
    record_summary("planner_engine", "ok", start_time, effect="goal_update", risk="low")
    return _expansion_payload_response(payload)
