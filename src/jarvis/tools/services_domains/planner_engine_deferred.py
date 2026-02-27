"""Deferred action handlers for planner engine."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def planner_deferred_schedule(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response
    _deferred_actions = s._deferred_actions
    DEFERRED_ACTION_MAX = s.DEFERRED_ACTION_MAX

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
    payload = {"action": "deferred_schedule", "scheduled": dict(_deferred_actions[action_id]), "deferred_count": len(_deferred_actions)}
    record_summary("planner_engine", "ok", start_time, effect="deferred_schedule", risk="low")
    return _expansion_payload_response(payload)


async def planner_deferred_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_int = s._as_int
    _expansion_payload_response = s._expansion_payload_response
    _deferred_actions = s._deferred_actions

    limit = _as_int(args.get("limit", 50), 50, minimum=1, maximum=200)
    rows = sorted(_deferred_actions.values(), key=lambda item: float(item.get("execute_at", 0.0)))[:limit]
    payload = {"action": "deferred_list", "deferred_count": len(_deferred_actions), "items": rows}
    record_summary("planner_engine", "ok", start_time, effect="deferred_list", risk="low")
    return _expansion_payload_response(payload)
