"""Plan action for planner engine."""

from __future__ import annotations

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
