"""Expansion and health contract field groups."""

from __future__ import annotations

from typing import Any

SYSTEM_STATUS_CONTRACT_EXPANSION_FIELDS: dict[str, Any] = {
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
