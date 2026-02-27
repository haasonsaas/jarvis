"""Runtime helpers for governance/status domain handlers."""

from __future__ import annotations

import copy
from typing import Any


def tool_policy_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    return {
        "allow_count": len(s._tool_allowlist),
        "deny_count": len(s._tool_denylist),
        "home_permission_profile": s._home_permission_profile,
        "safe_mode_enabled": s._safe_mode_enabled,
        "home_require_confirm_execute": bool(s._home_require_confirm_execute),
        "home_conversation_enabled": bool(s._home_conversation_enabled),
        "home_conversation_permission_profile": s._home_conversation_permission_profile,
        "todoist_permission_profile": s._todoist_permission_profile,
        "notification_permission_profile": s._notification_permission_profile,
        "nudge_policy": s._nudge_policy,
        "nudge_quiet_hours_start": s._nudge_quiet_hours_start,
        "nudge_quiet_hours_end": s._nudge_quiet_hours_end,
        "nudge_quiet_window_active": s._quiet_window_active(),
        "email_permission_profile": s._email_permission_profile,
        "memory_pii_guardrails_enabled": s._memory_pii_guardrails_enabled,
        "identity_enforcement_enabled": s._identity_enforcement_enabled,
        "identity_default_profile": s._identity_default_profile,
        "identity_require_approval": s._identity_require_approval,
        "plan_preview_require_ack": s._plan_preview_require_ack,
    }


def scorecard_context(
    services_module: Any,
    *,
    recent_tool_limit: int,
) -> dict[str, Any]:
    s = services_module
    memory_status: dict[str, Any] | None = None
    if s._memory is not None:
        try:
            memory_status = s._memory.memory_status()
        except Exception as exc:
            memory_status = {"error": str(exc)}

    try:
        recent_tools = s.list_summaries(limit=recent_tool_limit)
    except Exception as exc:
        recent_tools = {"error": str(exc)}
    identity_status = s._identity_status_snapshot()
    tool_policy_status = tool_policy_status_snapshot(s)
    observability_status = s._observability_snapshot()
    integrations_status = s._integration_health_snapshot()
    audit_status = s._audit_status()
    health = s._health_rollup(
        config_present=(s._config is not None),
        memory_state=memory_status if isinstance(memory_status, dict) else None,
        recent_tools=recent_tools,
        identity_status=identity_status,
    )
    return {
        "memory_status": memory_status,
        "recent_tools": recent_tools,
        "identity_status": identity_status,
        "tool_policy_status": tool_policy_status,
        "observability_status": observability_status,
        "integrations_status": integrations_status,
        "audit_status": audit_status,
        "health": health,
    }


def system_status_payload(
    services_module: Any,
    *,
    schema_version: str,
    scorecard: dict[str, Any],
    expansion_status: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    s = services_module
    _config = s._config
    return {
        "schema_version": schema_version,
        "local_time": s._now_local(),
        "home_assistant_configured": bool(_config and _config.has_home_assistant),
        "home_conversation_enabled": bool(s._home_conversation_enabled),
        "todoist_configured": bool(_config and str(_config.todoist_api_token).strip()),
        "pushover_configured": bool(
            _config
            and str(_config.pushover_api_token).strip()
            and str(_config.pushover_user_key).strip()
        ),
        "motion_enabled": bool(_config and _config.motion_enabled),
        "home_tools_enabled": bool(_config and _config.home_enabled),
        "memory_enabled": bool(_config and _config.memory_enabled),
        "backchannel_style": _config.backchannel_style if _config else "unknown",
        "persona_style": _config.persona_style if _config else "unknown",
        "tool_policy": context["tool_policy_status"],
        "timers": s._timer_status(),
        "reminders": s._reminder_status(),
        "voice_attention": s._voice_attention_snapshot(),
        "turn_timeouts": {
            "watchdog_enabled": bool(_config and getattr(_config, "watchdog_enabled", False)),
            "listen_sec": s._turn_timeout_listen_sec,
            "think_sec": s._turn_timeout_think_sec,
            "speak_sec": s._turn_timeout_speak_sec,
            "act_sec": s._turn_timeout_act_sec,
        },
        "integrations": context["integrations_status"],
        "identity": context["identity_status"],
        "skills": s._skills_status_snapshot(),
        "observability": context["observability_status"],
        "scorecard": scorecard,
        "plan_preview": {
            "pending_count": len(s._pending_plan_previews),
            "ttl_sec": s.PLAN_PREVIEW_TTL_SEC,
            "strict_mode": bool(s._plan_preview_require_ack),
        },
        "retention_policy": {
            "memory_retention_days": s._memory_retention_days,
            "audit_retention_days": s._audit_retention_days,
        },
        "recovery_journal": s._recovery_journal_status(limit=20),
        "dead_letter_queue": s._dead_letter_queue_status(limit=20, status_filter="all"),
        "expansion": expansion_status,
        "memory": context["memory_status"],
        "audit": context["audit_status"],
        "recent_tools": context["recent_tools"],
        "health": context["health"],
    }


_SYSTEM_STATUS_CONTRACT_FIELDS: dict[str, Any] = {
    "top_level_required": [
        "schema_version",
        "local_time",
        "home_assistant_configured",
        "home_conversation_enabled",
        "todoist_configured",
        "pushover_configured",
        "motion_enabled",
        "home_tools_enabled",
        "memory_enabled",
        "backchannel_style",
        "persona_style",
        "tool_policy",
        "timers",
        "reminders",
        "voice_attention",
        "turn_timeouts",
        "integrations",
        "identity",
        "skills",
        "observability",
        "scorecard",
        "plan_preview",
        "retention_policy",
        "recovery_journal",
        "dead_letter_queue",
        "expansion",
        "memory",
        "audit",
        "recent_tools",
        "health",
    ],
    "tool_policy_required": [
        "allow_count",
        "deny_count",
        "home_permission_profile",
        "safe_mode_enabled",
        "home_require_confirm_execute",
        "home_conversation_enabled",
        "home_conversation_permission_profile",
        "todoist_permission_profile",
        "notification_permission_profile",
        "nudge_policy",
        "nudge_quiet_hours_start",
        "nudge_quiet_hours_end",
        "nudge_quiet_window_active",
        "email_permission_profile",
        "memory_pii_guardrails_enabled",
        "identity_enforcement_enabled",
        "identity_default_profile",
        "identity_require_approval",
        "plan_preview_require_ack",
    ],
    "timers_required": [
        "active_count",
        "next_due_in_sec",
    ],
    "reminders_required": [
        "pending_count",
        "completed_count",
        "due_count",
        "next_due_in_sec",
    ],
    "voice_attention_required": [
        "mode",
        "followup_active",
        "sleeping",
        "active_room",
        "adaptive_silence_timeout_sec",
        "speech_rate_wps",
        "interruption_likelihood",
        "turn_choreography",
        "stt_diagnostics",
        "voice_profile_user",
        "voice_profile",
        "voice_profile_count",
        "acoustic_scene",
        "preference_learning",
        "multimodal_grounding",
    ],
    "voice_attention_acoustic_scene_required": [
        "last_doa_angle",
        "last_doa_speech",
        "last_doa_age_sec",
        "attention_confidence",
        "attention_source",
    ],
    "voice_attention_preference_learning_required": [
        "user",
        "updates",
        "applied_at",
        "source_text",
    ],
    "voice_attention_multimodal_grounding_required": [
        "overall_confidence",
        "confidence_band",
        "attention_source",
        "modality_scores",
        "signals",
        "reasons",
    ],
    "voice_attention_turn_choreography_required": [
        "phase",
        "label",
        "turn_lean",
        "turn_tilt",
        "turn_glance_yaw",
        "updated_at",
    ],
    "voice_attention_stt_diagnostics_required": [
        "source",
        "fallback_used",
        "confidence_score",
        "confidence_band",
        "avg_logprob",
        "avg_no_speech_prob",
        "language",
        "language_probability",
        "segment_count",
        "word_count",
        "char_count",
        "updated_at",
        "error",
    ],
    "voice_attention_voice_profile_required": [
        "verbosity",
        "confirmations",
        "pace",
        "tone",
    ],
    "turn_timeouts_required": [
        "watchdog_enabled",
        "listen_sec",
        "think_sec",
        "speak_sec",
        "act_sec",
    ],
    "integrations_required": [
        "home_assistant",
        "todoist",
        "pushover",
        "weather",
        "webhook",
        "email",
        "channels",
    ],
    "integration_circuit_breaker_required": [
        "open",
        "open_remaining_sec",
        "consecutive_failures",
        "opened_count",
        "cooldown_sec",
        "last_error",
        "last_failure_at",
        "last_success_at",
    ],
    "identity_required": [
        "enabled",
        "default_user",
        "default_profile",
        "require_approval",
        "approval_code_configured",
        "trusted_user_count",
        "trusted_users",
        "profile_count",
        "user_profiles",
        "trust_policy_count",
        "trust_policies",
        "guest_sessions_active",
        "guest_sessions",
        "household_profile_count",
        "household_profiles",
    ],
    "skills_required": [
        "enabled",
        "loaded_count",
        "enabled_count",
        "skills",
    ],
    "observability_required": [
        "enabled",
        "uptime_sec",
        "restart_count",
        "intent_metrics",
        "multimodal_metrics",
        "alerts",
        "latency_dashboards",
        "policy_decision_analytics",
    ],
    "observability_multimodal_metrics_required": [
        "turn_count",
        "avg_confidence",
        "low_confidence_count",
        "low_confidence_rate",
    ],
    "observability_intent_metrics_required": [
        "turn_count",
        "answer_intent_count",
        "action_intent_count",
        "hybrid_intent_count",
        "answer_sample_count",
        "completion_sample_count",
        "answer_quality_success_rate",
        "completion_success_rate",
        "correction_count",
        "correction_frequency",
        "preference_update_turns",
        "preference_update_fields",
    ],
    "observability_latency_dashboards_required": [
        "sample_count",
        "overall_total_ms",
        "by_intent",
        "by_tool_mix",
        "by_wake_mode",
    ],
    "observability_latency_bucket_required": [
        "p50",
        "p95",
        "p99",
    ],
    "observability_policy_decision_analytics_required": [
        "decision_count",
        "by_tool",
        "by_status",
        "by_reason",
        "by_user",
        "by_user_tool",
    ],
    "scorecard_required": [
        "overall",
        "dimensions",
        "weights",
        "computed_at",
    ],
    "scorecard_overall_required": [
        "score",
        "grade",
    ],
    "scorecard_dimensions_required": [
        "latency",
        "reliability",
        "initiative",
        "trust",
    ],
    "scorecard_dimension_required": [
        "score",
        "grade",
    ],
    "plan_preview_required": [
        "pending_count",
        "ttl_sec",
        "strict_mode",
    ],
    "retention_policy_required": [
        "memory_retention_days",
        "audit_retention_days",
    ],
    "recovery_journal_required": [
        "path",
        "exists",
        "entry_count",
        "tracked_actions",
        "unresolved_count",
        "interrupted_count",
        "recent",
    ],
    "dead_letter_queue_required": [
        "path",
        "exists",
        "entry_count",
        "pending_count",
        "failed_count",
        "replayed_count",
        "recent",
    ],
    "expansion_required": [
        "proactive",
        "memory_governance",
        "identity_trust",
        "home_orchestration",
        "skills_governance",
        "planner_engine",
        "quality_evaluator",
        "embodiment_presence",
        "integration_hub",
    ],
    "expansion_proactive_required": [
        "pending_follow_through_count",
        "digest_snoozed_until",
        "last_briefing_at",
        "last_digest_at",
        "nudge_decisions_total",
        "nudge_interrupt_total",
        "nudge_notify_total",
        "nudge_defer_total",
        "nudge_deduped_total",
        "last_nudge_decision_at",
        "last_nudge_dedupe_at",
        "nudge_recent_dispatch_count",
    ],
    "expansion_memory_governance_required": [
        "partition_overlay_count",
        "last_quality_audit",
    ],
    "expansion_identity_trust_required": [
        "trust_policy_count",
        "guest_session_count",
        "household_profile_count",
    ],
    "expansion_home_orchestration_required": [
        "area_policy_count",
        "tracked_task_count",
        "automation_draft_count",
        "automation_applied_count",
    ],
    "expansion_skills_governance_required": [
        "quota_count",
        "sandbox_templates",
    ],
    "expansion_planner_engine_required": [
        "task_graph_count",
        "deferred_action_count",
        "autonomy_task_count",
        "autonomy_waiting_checkpoint_count",
        "autonomy_last_cycle_at",
    ],
    "expansion_quality_evaluator_required": [
        "cached_report_count",
        "recent_reports",
    ],
    "expansion_embodiment_presence_required": [
        "micro_expression_count",
        "gaze_calibration_count",
        "gesture_profile_count",
        "privacy_posture",
        "motion_safety_envelope",
    ],
    "expansion_integration_hub_required": [
        "notes_backend_default",
        "notes_dir",
        "release_channels",
        "active_release_channel",
        "release_channel_config_path",
        "last_release_channel_check_at",
        "last_release_channel_check_channel",
        "last_release_channel_check_passed",
        "migration_checks",
    ],
    "health_required": [
        "health_level",
        "reasons",
    ],
}


def system_status_contract_payload(*, schema_version: str) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        **copy.deepcopy(_SYSTEM_STATUS_CONTRACT_FIELDS),
    }
