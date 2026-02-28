"""Runtime state bind/bootstrap helpers for services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.tools.services_runtime_state_persistence import load_expansion_state

def bind_runtime_state(services_module: Any, config: Any, memory_store: Any | None = None) -> None:
    s = services_module
    s._config = config
    s._memory = memory_store
    s._audit_log_max_bytes = int(config.audit_log_max_bytes)
    s._audit_log_backups = int(config.audit_log_backups)
    s._home_permission_profile = str(getattr(config, "home_permission_profile", "control")).strip().lower()
    if s._home_permission_profile not in {"readonly", "control"}:
        s._home_permission_profile = "control"
    s._home_require_confirm_execute = bool(getattr(config, "home_require_confirm_execute", False))
    s._home_conversation_enabled = bool(getattr(config, "home_conversation_enabled", False))
    s._home_conversation_permission_profile = str(
        getattr(config, "home_conversation_permission_profile", "readonly")
    ).strip().lower()
    if s._home_conversation_permission_profile not in {"readonly", "control"}:
        s._home_conversation_permission_profile = "readonly"
    s._todoist_permission_profile = str(getattr(config, "todoist_permission_profile", "control")).strip().lower()
    if s._todoist_permission_profile not in {"readonly", "control"}:
        s._todoist_permission_profile = "control"
    s._notification_permission_profile = str(
        getattr(config, "notification_permission_profile", "allow")
    ).strip().lower()
    if s._notification_permission_profile not in {"off", "allow"}:
        s._notification_permission_profile = "allow"
    s._nudge_policy = str(getattr(config, "nudge_policy", "adaptive")).strip().lower()
    if s._nudge_policy not in {"interrupt", "defer", "adaptive"}:
        s._nudge_policy = "adaptive"
    s._nudge_quiet_hours_start = str(getattr(config, "nudge_quiet_hours_start", "22:00")).strip()
    s._nudge_quiet_hours_end = str(getattr(config, "nudge_quiet_hours_end", "07:00")).strip()
    s._email_permission_profile = str(getattr(config, "email_permission_profile", "readonly")).strip().lower()
    if s._email_permission_profile not in {"readonly", "control"}:
        s._email_permission_profile = "readonly"
    s._todoist_timeout_sec = float(getattr(config, "todoist_timeout_sec", 10.0))
    s._pushover_timeout_sec = float(getattr(config, "pushover_timeout_sec", 10.0))
    s._email_smtp_host = str(getattr(config, "email_smtp_host", "")).strip()
    s._email_smtp_port = int(getattr(config, "email_smtp_port", 587))
    s._email_smtp_username = str(getattr(config, "email_smtp_username", "")).strip()
    s._email_smtp_password = str(getattr(config, "email_smtp_password", "")).strip()
    s._email_from = str(getattr(config, "email_from", "")).strip()
    s._email_default_to = str(getattr(config, "email_default_to", "")).strip()
    s._email_use_tls = bool(getattr(config, "email_use_tls", True))
    s._email_timeout_sec = float(getattr(config, "email_timeout_sec", 10.0))
    s._notion_api_token = str(getattr(config, "notion_api_token", "")).strip()
    s._notion_database_id = str(getattr(config, "notion_database_id", "")).strip()
    s._weather_units = str(getattr(config, "weather_units", "metric")).strip().lower()
    if s._weather_units not in {"metric", "imperial"}:
        s._weather_units = "metric"
    s._weather_timeout_sec = float(getattr(config, "weather_timeout_sec", 8.0))
    s._webhook_allowlist = [
        str(host).strip().lower()
        for host in getattr(config, "webhook_allowlist", [])
        if str(host).strip()
    ]
    s._webhook_auth_token = str(getattr(config, "webhook_auth_token", "")).strip()
    s._webhook_timeout_sec = float(getattr(config, "webhook_timeout_sec", 8.0))
    s._turn_timeout_listen_sec = float(getattr(config, "watchdog_listening_timeout_sec", 30.0))
    s._turn_timeout_think_sec = float(getattr(config, "watchdog_thinking_timeout_sec", 60.0))
    s._turn_timeout_speak_sec = float(getattr(config, "watchdog_speaking_timeout_sec", 45.0))
    s._turn_timeout_act_sec = float(getattr(config, "turn_timeout_act_sec", 30.0))
    s._slack_webhook_url = str(getattr(config, "slack_webhook_url", "")).strip()
    s._discord_webhook_url = str(getattr(config, "discord_webhook_url", "")).strip()
    s._identity_enforcement_enabled = bool(getattr(config, "identity_enforcement_enabled", False))
    s._identity_default_user = str(getattr(config, "identity_default_user", "owner")).strip().lower() or "owner"
    s._identity_default_profile = str(getattr(config, "identity_default_profile", "control")).strip().lower()
    if s._identity_default_profile not in {"deny", "readonly", "control", "trusted"}:
        s._identity_default_profile = "control"
    raw_profiles = getattr(config, "identity_user_profiles", {}) or {}
    if isinstance(raw_profiles, dict):
        s._identity_user_profiles = {
            str(user).strip().lower(): str(profile).strip().lower()
            for user, profile in raw_profiles.items()
            if str(user).strip()
            and str(profile).strip().lower() in {"deny", "readonly", "control", "trusted"}
        }
    else:
        s._identity_user_profiles = {}
    raw_trusted_users = getattr(config, "identity_trusted_users", []) or []
    s._identity_trusted_users = {
        str(user).strip().lower() for user in raw_trusted_users if str(user).strip()
    }
    s._identity_require_approval = bool(getattr(config, "identity_require_approval", True))
    s._identity_approval_code = str(getattr(config, "identity_approval_code", "")).strip()
    s._plan_preview_require_ack = bool(getattr(config, "plan_preview_require_ack", False))
    s._safe_mode_enabled = bool(getattr(config, "safe_mode_enabled", False))
    s._memory_retention_days = max(0.0, float(getattr(config, "memory_retention_days", 0.0)))
    s._audit_retention_days = max(0.0, float(getattr(config, "audit_retention_days", 0.0)))
    s._memory_pii_guardrails_enabled = bool(getattr(config, "memory_pii_guardrails_enabled", True))
    s._audit_encryption_enabled = bool(getattr(config, "audit_encryption_enabled", False))
    s._data_encryption_key = str(getattr(config, "data_encryption_key", "")).strip()
    s._recovery_journal_path = Path(
        str(getattr(config, "recovery_journal_path", str(s.DEFAULT_RECOVERY_JOURNAL)))
    ).expanduser()
    s._dead_letter_queue_path = Path(
        str(getattr(config, "dead_letter_queue_path", str(s.DEFAULT_DEAD_LETTER_QUEUE)))
    ).expanduser()
    s._expansion_state_path = Path(
        str(getattr(config, "expansion_state_path", str(s.DEFAULT_EXPANSION_STATE)))
    ).expanduser()
    s._release_channel_config_path = Path(
        str(getattr(config, "release_channel_config_path", str(s.DEFAULT_RELEASE_CHANNEL_CONFIG)))
    ).expanduser()
    s._policy_engine_path = Path(
        str(getattr(config, "policy_engine_path", str(s.DEFAULT_POLICY_ENGINE_CONFIG)))
    ).expanduser()
    s._quality_report_dir = Path(
        str(getattr(config, "quality_report_dir", str(s.QUALITY_REPORT_DIR_DEFAULT)))
    ).expanduser()
    s._notes_capture_dir = Path(
        str(getattr(config, "notes_capture_dir", str(s.NOTES_CAPTURE_DIR_DEFAULT)))
    ).expanduser()
    if not s._release_channel_config_path.is_absolute():
        s._release_channel_config_path = (Path.cwd() / s._release_channel_config_path).resolve()
    if not s._policy_engine_path.is_absolute():
        s._policy_engine_path = (Path.cwd() / s._policy_engine_path).resolve()
    if not s._quality_report_dir.is_absolute():
        s._quality_report_dir = (Path.cwd() / s._quality_report_dir).resolve()
    if not s._notes_capture_dir.is_absolute():
        s._notes_capture_dir = (Path.cwd() / s._notes_capture_dir).resolve()
    s._configure_audit_encryption(enabled=s._audit_encryption_enabled, key=s._data_encryption_key)
    _reset_runtime_state(s)
    s._load_policy_engine()
    for integration in sorted(set(s.INTEGRATION_TOOL_MAP.values())):
        s._ensure_circuit_breaker_state(integration)
    load_expansion_state(s)
    s._recovery_reconcile_interrupted()
    s._load_timers_from_store()
    s._load_reminders_from_store()
    s._tool_allowlist = list(config.tool_allowlist)
    s._tool_denylist = list(config.tool_denylist)
    s.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    s._apply_retention_policies()


def _reset_runtime_state(services_module: Any) -> None:
    s = services_module
    s._action_last_seen.clear()
    s._ha_state_cache.clear()
    s._timers.clear()
    s._timer_id_seq = 1
    s._reminders.clear()
    s._reminder_id_seq = 1
    s._email_history.clear()
    s._pending_plan_previews.clear()
    s._runtime_voice_state.clear()
    s._runtime_observability_state.clear()
    s._runtime_skills_state.clear()
    s._integration_circuit_breakers.clear()
    s._proactive_state["pending_follow_through"] = []
    s._proactive_state["follow_through_seq"] = 1
    s._proactive_state["follow_through_enqueued_total"] = 0
    s._proactive_state["follow_through_executed_total"] = 0
    s._proactive_state["follow_through_deduped_total"] = 0
    s._proactive_state["follow_through_pruned_total"] = 0
    s._proactive_state["last_follow_through_at"] = 0.0
    s._proactive_state["digest_snoozed_until"] = 0.0
    s._proactive_state["last_briefing_at"] = 0.0
    s._proactive_state["briefings_total"] = 0
    s._proactive_state["last_briefing_mode"] = ""
    s._proactive_state["last_digest_at"] = 0.0
    s._proactive_state["digests_total"] = 0
    s._proactive_state["digest_items_total"] = 0
    s._proactive_state["digest_deduped_total"] = 0
    s._proactive_state["nudge_decisions_total"] = 0
    s._proactive_state["nudge_interrupt_total"] = 0
    s._proactive_state["nudge_notify_total"] = 0
    s._proactive_state["nudge_defer_total"] = 0
    s._proactive_state["nudge_deduped_total"] = 0
    s._proactive_state["last_nudge_decision_at"] = 0.0
    s._proactive_state["last_nudge_dedupe_at"] = 0.0
    s._proactive_state["nudge_recent_dispatches"] = []
    s._proactive_state["approval_requests"] = []
    s._proactive_state["approval_seq"] = 1
    s._proactive_state["approval_requests_total"] = 0
    s._proactive_state["approval_approved_total"] = 0
    s._proactive_state["approval_rejected_total"] = 0
    s._proactive_state["approval_consumed_total"] = 0
    s._proactive_state["approval_expired_total"] = 0
    s._proactive_state["approval_pruned_total"] = 0
    s._proactive_state["effect_verification_total"] = 0
    s._proactive_state["effect_verification_passed_total"] = 0
    s._proactive_state["effect_verification_failed_total"] = 0
    s._proactive_state["autonomy_replan_seq"] = 1
    s._proactive_state["identity_trust_scores"] = {}
    s._policy_engine = s._normalize_policy_engine({})
    s._memory_partition_overlays.clear()
    s._memory_quality_last.clear()
    s._identity_trust_policies.clear()
    s._guest_sessions.clear()
    s._household_profiles.clear()
    s._home_area_policies.clear()
    s._home_task_runs.clear()
    s._home_automation_drafts.clear()
    s._home_automation_applied.clear()
    s._skill_quotas.clear()
    s._planner_task_graphs.clear()
    s._deferred_actions.clear()
    s._autonomy_checkpoints.clear()
    s._autonomy_cycle_history.clear()
    s._autonomy_replan_drafts.clear()
    s._world_model_state["entities"] = {}
    s._world_model_state["facts"] = {}
    s._world_model_state["events"] = []
    s._world_model_state["updated_at"] = 0.0
    s._goal_stack.clear()
    s._identity_step_up_tokens.clear()
    s._autonomy_slo_state["updated_at"] = 0.0
    s._autonomy_slo_state["window_size"] = 50
    s._autonomy_slo_state["metrics"] = {}
    s._autonomy_slo_state["alerts"] = []
    s._quality_reports.clear()
    s._micro_expression_library.clear()
    s._gaze_calibrations.clear()
    s._gesture_envelopes.clear()
    s._privacy_posture["state"] = "normal"
    s._privacy_posture["reason"] = "startup"
    s._privacy_posture["updated_at"] = 0.0
    s._motion_safety_envelope["updated_at"] = 0.0
    s._release_channel_state["active_channel"] = "dev"
    s._release_channel_state["last_check_at"] = 0.0
    s._release_channel_state["last_check_channel"] = ""
    s._release_channel_state["last_check_passed"] = False
    s._release_channel_state["migration_checks"] = []
    s._home_task_seq = 1
    s._home_automation_seq = 1
    s._planner_task_seq = 1
    s._deferred_action_seq = 1
