"""Expansion and health-rollup status snapshot helpers."""

from __future__ import annotations

from typing import Any


def expansion_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    s._prune_guest_sessions()
    now = s.time.time()
    approval_rows = (
        [row for row in s._proactive_state.get("approval_requests", []) if isinstance(row, dict)]
        if isinstance(s._proactive_state.get("approval_requests"), list)
        else []
    )
    approval_pending_count = 0
    for row in approval_rows:
        status = str(row.get("status", "")).strip().lower()
        expires_at = float(row.get("expires_at", 0.0) or 0.0)
        if status == "pending" and (expires_at <= 0.0 or expires_at > now):
            approval_pending_count += 1
    autonomy_rows = [
        row
        for row in s._deferred_actions.values()
        if isinstance(row, dict) and str(row.get("kind", "")).strip().lower() == "autonomy_task"
    ]
    autonomy_in_progress_count = 0
    autonomy_backlog_step_count = 0
    autonomy_needs_replan_count = 0
    autonomy_retry_pending_count = 0
    autonomy_failure_taxonomy: dict[str, int] = {}
    for row in autonomy_rows:
        status = str(row.get("status", "")).strip().lower()
        if status == "needs_replan":
            autonomy_needs_replan_count += 1
        if isinstance(row.get("plan_step_attempts"), dict) and row.get("plan_step_attempts"):
            autonomy_retry_pending_count += 1
        if isinstance(row.get("failure_taxonomy"), dict):
            for key, value in row.get("failure_taxonomy", {}).items():
                reason_code = str(key).strip().lower()
                if not reason_code:
                    continue
                autonomy_failure_taxonomy[reason_code] = autonomy_failure_taxonomy.get(reason_code, 0) + s._as_int(
                    value,
                    0,
                    minimum=0,
                    maximum=10_000,
                )
        total_steps = s._as_int(row.get("plan_total_steps", 0), 0, minimum=0, maximum=1000)
        step_index = s._as_int(row.get("plan_step_index", 0), 0, minimum=0, maximum=max(0, total_steps))
        if total_steps > 0:
            autonomy_backlog_step_count += max(0, total_steps - step_index)
            if (
                status in {"scheduled", "waiting_checkpoint"}
                and step_index > 0
            ):
                autonomy_in_progress_count += 1
    return {
        "proactive": {
            "pending_follow_through_count": len(s._proactive_state.get("pending_follow_through", [])),
            "follow_through_seq": int(s._proactive_state.get("follow_through_seq", 1) or 1),
            "follow_through_enqueued_total": int(s._proactive_state.get("follow_through_enqueued_total", 0) or 0),
            "follow_through_executed_total": int(s._proactive_state.get("follow_through_executed_total", 0) or 0),
            "follow_through_deduped_total": int(s._proactive_state.get("follow_through_deduped_total", 0) or 0),
            "follow_through_pruned_total": int(s._proactive_state.get("follow_through_pruned_total", 0) or 0),
            "last_follow_through_at": float(s._proactive_state.get("last_follow_through_at", 0.0) or 0.0),
            "digest_snoozed_until": float(s._proactive_state.get("digest_snoozed_until", 0.0) or 0.0),
            "last_briefing_at": float(s._proactive_state.get("last_briefing_at", 0.0) or 0.0),
            "briefings_total": int(s._proactive_state.get("briefings_total", 0) or 0),
            "last_briefing_mode": str(s._proactive_state.get("last_briefing_mode", "")),
            "last_digest_at": float(s._proactive_state.get("last_digest_at", 0.0) or 0.0),
            "digests_total": int(s._proactive_state.get("digests_total", 0) or 0),
            "digest_items_total": int(s._proactive_state.get("digest_items_total", 0) or 0),
            "digest_deduped_total": int(s._proactive_state.get("digest_deduped_total", 0) or 0),
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
            "approval_pending_count": approval_pending_count,
            "approval_requests_total": int(s._proactive_state.get("approval_requests_total", 0) or 0),
            "approval_approved_total": int(s._proactive_state.get("approval_approved_total", 0) or 0),
            "approval_rejected_total": int(s._proactive_state.get("approval_rejected_total", 0) or 0),
            "approval_consumed_total": int(s._proactive_state.get("approval_consumed_total", 0) or 0),
            "approval_expired_total": int(s._proactive_state.get("approval_expired_total", 0) or 0),
            "effect_verification_total": int(s._proactive_state.get("effect_verification_total", 0) or 0),
            "effect_verification_passed_total": int(s._proactive_state.get("effect_verification_passed_total", 0) or 0),
            "effect_verification_failed_total": int(s._proactive_state.get("effect_verification_failed_total", 0) or 0),
            "identity_trust_score_count": (
                len(s._proactive_state.get("identity_trust_scores", {}))
                if isinstance(s._proactive_state.get("identity_trust_scores"), dict)
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
            "step_up_token_count": len(s._identity_step_up_tokens),
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
            "autonomy_task_count": len(autonomy_rows),
            "autonomy_waiting_checkpoint_count": sum(
                1
                for row in autonomy_rows
                if str(row.get("status", "")).strip().lower() == "waiting_checkpoint"
            ),
            "autonomy_in_progress_count": autonomy_in_progress_count,
            "autonomy_backlog_step_count": autonomy_backlog_step_count,
            "autonomy_needs_replan_count": autonomy_needs_replan_count,
            "autonomy_retry_pending_count": autonomy_retry_pending_count,
            "autonomy_failure_taxonomy": autonomy_failure_taxonomy,
            "autonomy_last_cycle_at": (
                float(s._autonomy_cycle_history[-1].get("timestamp", 0.0))
                if s._autonomy_cycle_history
                else 0.0
            ),
            "autonomy_replan_draft_count": len(s._autonomy_replan_drafts),
            "goal_stack_depth": len(s._goal_stack),
            "world_model_entity_count": len(s._world_model_state.get("entities", {}))
            if isinstance(s._world_model_state.get("entities"), dict)
            else 0,
            "world_model_event_count": len(s._world_model_state.get("events", []))
            if isinstance(s._world_model_state.get("events"), list)
            else 0,
            "autonomy_slo": (
                {
                    "updated_at": float(s._autonomy_slo_state.get("updated_at", 0.0) or 0.0),
                    "metrics": (
                        {
                            str(key): s._json_safe_clone(value)
                            for key, value in s._autonomy_slo_state.get("metrics", {}).items()
                        }
                        if isinstance(s._autonomy_slo_state.get("metrics"), dict)
                        else {}
                    ),
                    "alert_count": (
                        len(s._autonomy_slo_state.get("alerts", []))
                        if isinstance(s._autonomy_slo_state.get("alerts"), list)
                        else 0
                    ),
                }
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
            "policy_engine_version": str(s._policy_engine.get("version", "unknown")),
            "policy_engine_path": str(s._policy_engine_path),
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
