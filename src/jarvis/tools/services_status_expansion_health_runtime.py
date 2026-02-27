"""Expansion and health-rollup status snapshot helpers."""

from __future__ import annotations

from typing import Any

def expansion_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    s._prune_guest_sessions()
    return {
        "proactive": {
            "pending_follow_through_count": len(s._proactive_state.get("pending_follow_through", [])),
            "digest_snoozed_until": float(s._proactive_state.get("digest_snoozed_until", 0.0) or 0.0),
            "last_briefing_at": float(s._proactive_state.get("last_briefing_at", 0.0) or 0.0),
            "last_digest_at": float(s._proactive_state.get("last_digest_at", 0.0) or 0.0),
            "nudge_decisions_total": int(s._proactive_state.get("nudge_decisions_total", 0) or 0),
            "nudge_interrupt_total": int(s._proactive_state.get("nudge_interrupt_total", 0) or 0),
            "nudge_notify_total": int(s._proactive_state.get("nudge_notify_total", 0) or 0),
            "nudge_defer_total": int(s._proactive_state.get("nudge_defer_total", 0) or 0),
            "nudge_deduped_total": int(s._proactive_state.get("nudge_deduped_total", 0) or 0),
            "last_nudge_decision_at": float(s._proactive_state.get("last_nudge_decision_at", 0.0) or 0.0),
            "last_nudge_dedupe_at": float(s._proactive_state.get("last_nudge_dedupe_at", 0.0) or 0.0),
            "nudge_recent_dispatch_count": (
                len(s._proactive_state.get("nudge_recent_dispatches", []))
                if isinstance(s._proactive_state.get("nudge_recent_dispatches"), list)
                else 0
            ),
        },
        "memory_governance": {
            "partition_overlay_count": len(s._memory_partition_overlays),
            "last_quality_audit": dict(s._memory_quality_last) if isinstance(s._memory_quality_last, dict) else {},
        },
        "identity_trust": {
            "trust_policy_count": len(s._identity_trust_policies),
            "guest_session_count": len(s._guest_sessions),
            "household_profile_count": len(s._household_profiles),
        },
        "home_orchestration": {
            "area_policy_count": len(s._home_area_policies),
            "tracked_task_count": len(s._home_task_runs),
            "automation_draft_count": len(s._home_automation_drafts),
            "automation_applied_count": len(s._home_automation_applied),
        },
        "skills_governance": {
            "quota_count": len(s._skill_quotas),
            "sandbox_templates": sorted(s.SKILL_SANDBOX_TEMPLATES),
        },
        "planner_engine": {
            "task_graph_count": len(s._planner_task_graphs),
            "deferred_action_count": len(s._deferred_actions),
            "autonomy_task_count": sum(
                1
                for row in s._deferred_actions.values()
                if isinstance(row, dict) and str(row.get("kind", "")).strip().lower() == "autonomy_task"
            ),
            "autonomy_waiting_checkpoint_count": sum(
                1
                for row in s._deferred_actions.values()
                if isinstance(row, dict)
                and str(row.get("kind", "")).strip().lower() == "autonomy_task"
                and str(row.get("status", "")).strip().lower() == "waiting_checkpoint"
            ),
            "autonomy_last_cycle_at": (
                float(s._autonomy_cycle_history[-1].get("timestamp", 0.0))
                if s._autonomy_cycle_history
                else 0.0
            ),
        },
        "quality_evaluator": {
            "cached_report_count": len(s._quality_reports),
            "recent_reports": s._quality_reports_snapshot(limit=5),
        },
        "embodiment_presence": {
            "micro_expression_count": len(s._micro_expression_library),
            "gaze_calibration_count": len(s._gaze_calibrations),
            "gesture_profile_count": len(s._gesture_envelopes),
            "privacy_posture": dict(s._privacy_posture),
            "motion_safety_envelope": dict(s._motion_safety_envelope),
        },
        "integration_hub": {
            "notes_backend_default": "local_markdown",
            "notes_dir": str(s._notes_capture_dir),
            "release_channels": sorted(s.RELEASE_CHANNELS),
            "active_release_channel": str(s._release_channel_state.get("active_channel", "dev")),
            "release_channel_config_path": str(s._release_channel_config_path),
            "last_release_channel_check_at": float(s._release_channel_state.get("last_check_at", 0.0) or 0.0),
            "last_release_channel_check_channel": str(s._release_channel_state.get("last_check_channel", "")),
            "last_release_channel_check_passed": bool(s._release_channel_state.get("last_check_passed", False)),
            "migration_checks": [
                s._json_safe_clone(row)
                for row in (s._release_channel_state.get("migration_checks") or [])
                if isinstance(row, dict)
            ][:20],
        },
    }


def health_rollup(
    *,
    config_present: bool,
    memory_state: dict[str, Any] | None,
    recent_tools: list[dict[str, object]] | dict[str, str],
    identity_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    level = "ok"
    if not config_present:
        level = "error"
        reasons.append("config_unbound")
    if isinstance(memory_state, dict) and "error" in memory_state:
        reasons.append("memory_error")
    if isinstance(recent_tools, dict) and "error" in recent_tools:
        reasons.append("tool_summary_error")
    if isinstance(identity_status, dict):
        if (
            bool(identity_status.get("enabled"))
            and bool(identity_status.get("require_approval"))
            and not bool(identity_status.get("approval_code_configured"))
            and int(identity_status.get("trusted_user_count", 0) or 0) <= 0
        ):
            reasons.append("identity_approval_unconfigured")
    if reasons and level != "error":
        level = "degraded"
    return {"health_level": level, "reasons": reasons}
