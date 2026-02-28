"""Runtime state serialization/persist helpers for services."""

from __future__ import annotations

import json
import time
from typing import Any

def json_safe_clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe_clone(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_clone(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def replace_state_dict(services_module: Any, target: dict[str, Any], source: Any) -> None:
    s = services_module
    target.clear()
    if not isinstance(source, dict):
        return
    target.update({str(key): s._json_safe_clone(value) for key, value in source.items()})


def expansion_state_payload(services_module: Any) -> dict[str, Any]:
    s = services_module
    return {
        "version": 1,
        "saved_at": time.time(),
        "proactive_state": s._json_safe_clone(s._proactive_state),
        "policy_engine": s._json_safe_clone(s._policy_engine),
        "memory_partition_overlays": s._json_safe_clone(s._memory_partition_overlays),
        "memory_quality_last": s._json_safe_clone(s._memory_quality_last),
        "identity_trust_policies": s._json_safe_clone(s._identity_trust_policies),
        "guest_sessions": s._json_safe_clone(s._guest_sessions),
        "household_profiles": s._json_safe_clone(s._household_profiles),
        "home_area_policies": s._json_safe_clone(s._home_area_policies),
        "home_task_runs": s._json_safe_clone(s._home_task_runs),
        "home_task_seq": int(s._home_task_seq),
        "home_automation_drafts": s._json_safe_clone(s._home_automation_drafts),
        "home_automation_applied": s._json_safe_clone(s._home_automation_applied),
        "home_automation_seq": int(s._home_automation_seq),
        "skill_quotas": s._json_safe_clone(s._skill_quotas),
        "planner_task_graphs": s._json_safe_clone(s._planner_task_graphs),
        "planner_task_seq": int(s._planner_task_seq),
        "deferred_actions": s._json_safe_clone(s._deferred_actions),
        "deferred_action_seq": int(s._deferred_action_seq),
        "autonomy_checkpoints": s._json_safe_clone(s._autonomy_checkpoints),
        "autonomy_cycle_history": s._json_safe_clone(
            s._autonomy_cycle_history[-s.AUTONOMY_CYCLE_HISTORY_MAX :]
        ),
        "autonomy_replan_drafts": s._json_safe_clone(s._autonomy_replan_drafts),
        "world_model_state": s._json_safe_clone(s._world_model_state),
        "goal_stack": s._json_safe_clone(s._goal_stack[-s.GOAL_STACK_MAX :]),
        "identity_step_up_tokens": s._json_safe_clone(s._identity_step_up_tokens),
        "autonomy_slo_state": s._json_safe_clone(s._autonomy_slo_state),
        "quality_reports": s._json_safe_clone(s._quality_reports[-s.CACHED_QUALITY_REPORT_MAX :]),
        "micro_expression_library": s._json_safe_clone(s._micro_expression_library),
        "gaze_calibrations": s._json_safe_clone(s._gaze_calibrations),
        "gesture_envelopes": s._json_safe_clone(s._gesture_envelopes),
        "privacy_posture": s._json_safe_clone(s._privacy_posture),
        "motion_safety_envelope": s._json_safe_clone(s._motion_safety_envelope),
        "release_channel_state": s._json_safe_clone(s._release_channel_state),
    }


def persist_expansion_state(services_module: Any) -> None:
    s = services_module
    path = s._expansion_state_path
    payload = expansion_state_payload(s)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError:
        s.log.warning("Failed to persist expansion state", exc_info=True)
