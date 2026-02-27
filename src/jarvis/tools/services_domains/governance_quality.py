"""Quality and embodiment governance handlers."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.governance_quality_embodiment_actions import (
    embodiment_expression_library,
    embodiment_gaze_calibrate,
    embodiment_gesture_profile,
    embodiment_privacy_posture,
    embodiment_safety_envelope,
    embodiment_status,
)
from jarvis.tools.services_domains.governance_quality_evaluator_actions import (
    quality_eval_dataset_run,
    quality_eval_reports_list,
    quality_eval_weekly_report,
)


def _services():
    from jarvis.tools import services as s

    return s


async def quality_evaluator(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("quality_evaluator"):
        record_summary("quality_evaluator", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "weekly_report":
        return await quality_eval_weekly_report(args, start_time=start_time)
    if action == "dataset_run":
        return await quality_eval_dataset_run(args, start_time=start_time)
    if action == "reports_list":
        return await quality_eval_reports_list(args, start_time=start_time)

    _record_service_error("quality_evaluator", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown quality_evaluator action."}]}


async def embodiment_presence(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("embodiment_presence"):
        record_summary("embodiment_presence", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "expression_library":
        return await embodiment_expression_library(args, start_time=start_time)
    if action == "gaze_calibrate":
        return await embodiment_gaze_calibrate(args, start_time=start_time)
    if action == "gesture_profile":
        return await embodiment_gesture_profile(args, start_time=start_time)
    if action == "privacy_posture":
        return await embodiment_privacy_posture(args, start_time=start_time)
    if action == "safety_envelope":
        return await embodiment_safety_envelope(args, start_time=start_time)
    if action == "status":
        return await embodiment_status(args, start_time=start_time)

    _record_service_error("embodiment_presence", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown embodiment_presence action."}]}
