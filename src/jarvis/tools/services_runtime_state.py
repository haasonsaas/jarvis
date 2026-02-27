"""Runtime bind/bootstrap and expansion-state helpers for services."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


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
    s._quality_report_dir = Path(
        str(getattr(config, "quality_report_dir", str(s.QUALITY_REPORT_DIR_DEFAULT)))
    ).expanduser()
    s._notes_capture_dir = Path(
        str(getattr(config, "notes_capture_dir", str(s.NOTES_CAPTURE_DIR_DEFAULT)))
    ).expanduser()
    if not s._release_channel_config_path.is_absolute():
        s._release_channel_config_path = (Path.cwd() / s._release_channel_config_path).resolve()
    if not s._quality_report_dir.is_absolute():
        s._quality_report_dir = (Path.cwd() / s._quality_report_dir).resolve()
    if not s._notes_capture_dir.is_absolute():
        s._notes_capture_dir = (Path.cwd() / s._notes_capture_dir).resolve()
    s._configure_audit_encryption(enabled=s._audit_encryption_enabled, key=s._data_encryption_key)
    _reset_runtime_state(s)
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
    s._proactive_state["digest_snoozed_until"] = 0.0
    s._proactive_state["last_briefing_at"] = 0.0
    s._proactive_state["last_digest_at"] = 0.0
    s._proactive_state["nudge_decisions_total"] = 0
    s._proactive_state["nudge_interrupt_total"] = 0
    s._proactive_state["nudge_notify_total"] = 0
    s._proactive_state["nudge_defer_total"] = 0
    s._proactive_state["nudge_deduped_total"] = 0
    s._proactive_state["last_nudge_decision_at"] = 0.0
    s._proactive_state["last_nudge_dedupe_at"] = 0.0
    s._proactive_state["nudge_recent_dispatches"] = []
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


def quality_reports_snapshot(services_module: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    s = services_module
    if not s._quality_reports:
        return []
    capped = s._as_int(limit, 10, minimum=1, maximum=50)
    return [dict(item) for item in s._quality_reports[-capped:]][::-1]


def append_quality_report(services_module: Any, report: dict[str, Any]) -> None:
    s = services_module
    s._quality_reports.append({str(key): value for key, value in report.items()})
    if len(s._quality_reports) > s.CACHED_QUALITY_REPORT_MAX:
        del s._quality_reports[: len(s._quality_reports) - s.CACHED_QUALITY_REPORT_MAX]
    s._persist_expansion_state()


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


def load_expansion_state(services_module: Any) -> None:
    s = services_module
    path = s._expansion_state_path
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        s.log.warning("Failed to load expansion state", exc_info=True)
        return
    if not isinstance(payload, dict):
        return

    proactive = payload.get("proactive_state")
    if isinstance(proactive, dict):
        pending = proactive.get("pending_follow_through")
        s._proactive_state["pending_follow_through"] = (
            [s._json_safe_clone(row) for row in pending if isinstance(row, dict)]
            if isinstance(pending, list)
            else []
        )
        s._proactive_state["digest_snoozed_until"] = s._as_float(
            proactive.get("digest_snoozed_until", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["last_briefing_at"] = s._as_float(
            proactive.get("last_briefing_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["last_digest_at"] = s._as_float(
            proactive.get("last_digest_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["nudge_decisions_total"] = s._as_int(
            proactive.get("nudge_decisions_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_interrupt_total"] = s._as_int(
            proactive.get("nudge_interrupt_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_notify_total"] = s._as_int(
            proactive.get("nudge_notify_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_defer_total"] = s._as_int(
            proactive.get("nudge_defer_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_deduped_total"] = s._as_int(
            proactive.get("nudge_deduped_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["last_nudge_decision_at"] = s._as_float(
            proactive.get("last_nudge_decision_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["last_nudge_dedupe_at"] = s._as_float(
            proactive.get("last_nudge_dedupe_at", 0.0),
            0.0,
            minimum=0.0,
        )
        recent_dispatches = proactive.get("nudge_recent_dispatches")
        s._proactive_state["nudge_recent_dispatches"] = []
        if isinstance(recent_dispatches, list):
            for row in recent_dispatches[-s.NUDGE_RECENT_DISPATCH_MAX :]:
                if not isinstance(row, dict):
                    continue
                fingerprint = str(row.get("fingerprint", "")).strip()
                if not fingerprint:
                    continue
                dispatched_at = s._as_float(row.get("dispatched_at", 0.0), 0.0, minimum=0.0)
                s._proactive_state["nudge_recent_dispatches"].append(
                    {"fingerprint": fingerprint, "dispatched_at": dispatched_at}
                )

    replace_state_dict(s, s._memory_partition_overlays, payload.get("memory_partition_overlays"))
    replace_state_dict(s, s._memory_quality_last, payload.get("memory_quality_last"))
    replace_state_dict(s, s._identity_trust_policies, payload.get("identity_trust_policies"))
    replace_state_dict(s, s._household_profiles, payload.get("household_profiles"))
    replace_state_dict(s, s._home_area_policies, payload.get("home_area_policies"))
    replace_state_dict(s, s._home_task_runs, payload.get("home_task_runs"))
    replace_state_dict(s, s._home_automation_drafts, payload.get("home_automation_drafts"))
    replace_state_dict(s, s._home_automation_applied, payload.get("home_automation_applied"))
    replace_state_dict(s, s._skill_quotas, payload.get("skill_quotas"))
    replace_state_dict(s, s._planner_task_graphs, payload.get("planner_task_graphs"))
    replace_state_dict(s, s._deferred_actions, payload.get("deferred_actions"))
    replace_state_dict(s, s._autonomy_checkpoints, payload.get("autonomy_checkpoints"))
    replace_state_dict(s, s._micro_expression_library, payload.get("micro_expression_library"))
    replace_state_dict(s, s._gaze_calibrations, payload.get("gaze_calibrations"))
    replace_state_dict(s, s._gesture_envelopes, payload.get("gesture_envelopes"))

    autonomy_history = payload.get("autonomy_cycle_history")
    s._autonomy_cycle_history.clear()
    if isinstance(autonomy_history, list):
        for row in autonomy_history[-s.AUTONOMY_CYCLE_HISTORY_MAX :]:
            if isinstance(row, dict):
                s._autonomy_cycle_history.append(
                    {str(key): s._json_safe_clone(value) for key, value in row.items()}
                )

    s._guest_sessions.clear()
    guest_sessions = payload.get("guest_sessions")
    if isinstance(guest_sessions, dict):
        now = time.time()
        for raw_token, raw_row in guest_sessions.items():
            token = str(raw_token).strip()
            if not token or not isinstance(raw_row, dict):
                continue
            expires_at = s._as_float(raw_row.get("expires_at", 0.0), 0.0, minimum=0.0)
            if expires_at <= now:
                continue
            issued_at = s._as_float(raw_row.get("issued_at", 0.0), 0.0, minimum=0.0)
            guest_id = str(raw_row.get("guest_id", "guest")).strip().lower() or "guest"
            capabilities = sorted(set(s._as_str_list(raw_row.get("capabilities"), lower=True)))
            s._guest_sessions[token] = {
                "token": token,
                "guest_id": guest_id,
                "capabilities": capabilities,
                "issued_at": issued_at,
                "expires_at": expires_at,
            }

    quality_rows = payload.get("quality_reports")
    s._quality_reports.clear()
    if isinstance(quality_rows, list):
        for row in quality_rows[-s.CACHED_QUALITY_REPORT_MAX :]:
            if isinstance(row, dict):
                s._quality_reports.append({str(key): s._json_safe_clone(value) for key, value in row.items()})

    privacy_posture = payload.get("privacy_posture")
    if isinstance(privacy_posture, dict):
        s._privacy_posture["state"] = str(privacy_posture.get("state", "normal")).strip().lower() or "normal"
        s._privacy_posture["reason"] = str(privacy_posture.get("reason", "startup")).strip() or "startup"
        s._privacy_posture["updated_at"] = s._as_float(
            privacy_posture.get("updated_at", 0.0),
            0.0,
            minimum=0.0,
        )

    motion_envelope = payload.get("motion_safety_envelope")
    if isinstance(motion_envelope, dict):
        s._motion_safety_envelope["proximity_limit_cm"] = s._as_float(
            motion_envelope.get(
                "proximity_limit_cm",
                s._motion_safety_envelope.get("proximity_limit_cm", 35.0),
            ),
            s._as_float(s._motion_safety_envelope.get("proximity_limit_cm", 35.0), 35.0),
            minimum=5.0,
            maximum=300.0,
        )
        s._motion_safety_envelope["max_yaw_deg"] = s._as_float(
            motion_envelope.get("max_yaw_deg", s._motion_safety_envelope.get("max_yaw_deg", 45.0)),
            s._as_float(s._motion_safety_envelope.get("max_yaw_deg", 45.0), 45.0),
            minimum=0.0,
            maximum=180.0,
        )
        s._motion_safety_envelope["max_pitch_deg"] = s._as_float(
            motion_envelope.get("max_pitch_deg", s._motion_safety_envelope.get("max_pitch_deg", 20.0)),
            s._as_float(s._motion_safety_envelope.get("max_pitch_deg", 20.0), 20.0),
            minimum=0.0,
            maximum=90.0,
        )
        s._motion_safety_envelope["max_roll_deg"] = s._as_float(
            motion_envelope.get("max_roll_deg", s._motion_safety_envelope.get("max_roll_deg", 15.0)),
            s._as_float(s._motion_safety_envelope.get("max_roll_deg", 15.0), 15.0),
            minimum=0.0,
            maximum=90.0,
        )
        s._motion_safety_envelope["hardware_state"] = (
            str(motion_envelope.get("hardware_state", "normal")).strip().lower() or "normal"
        )
        s._motion_safety_envelope["updated_at"] = s._as_float(
            motion_envelope.get("updated_at", 0.0),
            0.0,
            minimum=0.0,
        )

    release_state = payload.get("release_channel_state")
    if isinstance(release_state, dict):
        channel = str(release_state.get("active_channel", "dev")).strip().lower()
        if channel not in s.RELEASE_CHANNELS:
            channel = "dev"
        s._release_channel_state["active_channel"] = channel
        s._release_channel_state["last_check_at"] = s._as_float(
            release_state.get("last_check_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._release_channel_state["last_check_channel"] = (
            str(release_state.get("last_check_channel", channel)).strip().lower() or channel
        )
        s._release_channel_state["last_check_passed"] = bool(release_state.get("last_check_passed", False))
        migration_checks = release_state.get("migration_checks")
        s._release_channel_state["migration_checks"] = (
            [s._json_safe_clone(row) for row in migration_checks if isinstance(row, dict)]
            if isinstance(migration_checks, list)
            else []
        )

    s._home_task_seq = s._as_int(payload.get("home_task_seq", 1), 1, minimum=1)
    s._home_automation_seq = s._as_int(payload.get("home_automation_seq", 1), 1, minimum=1)
    s._planner_task_seq = s._as_int(payload.get("planner_task_seq", 1), 1, minimum=1)
    s._deferred_action_seq = s._as_int(payload.get("deferred_action_seq", 1), 1, minimum=1)
    s._prune_guest_sessions()
