"""Self-critique action for planner engine."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


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
