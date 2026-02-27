"""Status/snapshot runtime helpers for services domains."""

from __future__ import annotations

from typing import Any


def integration_health_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    home_configured = bool(s._config and s._config.has_home_assistant)
    todoist_configured = bool(s._config and str(s._config.todoist_api_token).strip())
    pushover_configured = bool(
        s._config and str(s._config.pushover_api_token).strip() and str(s._config.pushover_user_key).strip()
    )
    return {
        "home_assistant": {
            "configured": home_configured,
            "home_enabled": bool(s._config and s._config.home_enabled),
            "permission_profile": s._home_permission_profile,
            "circuit_breaker": s._integration_circuit_snapshot("home_assistant"),
        },
        "todoist": {
            "configured": todoist_configured,
            "permission_profile": s._todoist_permission_profile,
            "circuit_breaker": s._integration_circuit_snapshot("todoist"),
        },
        "pushover": {
            "configured": pushover_configured,
            "permission_profile": s._notification_permission_profile,
            "circuit_breaker": s._integration_circuit_snapshot("pushover"),
        },
        "weather": {
            "provider": "open-meteo",
            "units_default": s._weather_units,
            "timeout_sec": s._weather_timeout_sec,
            "circuit_breaker": s._integration_circuit_snapshot("weather"),
        },
        "webhook": {
            "allowlist_count": len(s._webhook_allowlist),
            "auth_token_configured": bool(s._webhook_auth_token),
            "timeout_sec": s._webhook_timeout_sec,
            "inbound_events": len(s._inbound_webhook_events),
            "circuit_breaker": s._integration_circuit_snapshot("webhook"),
        },
        "email": {
            "configured": bool(s._email_smtp_host and s._email_from and s._email_default_to),
            "permission_profile": s._email_permission_profile,
            "timeout_sec": s._email_timeout_sec,
            "circuit_breaker": s._integration_circuit_snapshot("email"),
        },
        "channels": {
            "slack_configured": bool(s._slack_webhook_url),
            "discord_configured": bool(s._discord_webhook_url),
            "circuit_breaker": s._integration_circuit_snapshot("channels"),
        },
    }


def identity_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    s._prune_guest_sessions()
    return {
        "enabled": s._identity_enforcement_enabled,
        "default_user": s._identity_default_user,
        "default_profile": s._identity_default_profile,
        "require_approval": s._identity_require_approval,
        "approval_code_configured": bool(s._identity_approval_code),
        "trusted_user_count": len(s._identity_trusted_users),
        "trusted_users": sorted(s._identity_trusted_users),
        "profile_count": len(s._identity_user_profiles),
        "user_profiles": {user: s._identity_user_profiles[user] for user in sorted(s._identity_user_profiles)},
        "trust_policy_count": len(s._identity_trust_policies),
        "trust_policies": {domain: dict(policy) for domain, policy in sorted(s._identity_trust_policies.items())},
        "guest_sessions_active": len(s._guest_sessions),
        "guest_sessions": [
            {
                "guest_id": str(item.get("guest_id", "")),
                "expires_at": float(item.get("expires_at", 0.0) or 0.0),
                "capabilities": s._as_str_list(item.get("capabilities"), lower=True),
            }
            for _, item in sorted(s._guest_sessions.items(), key=lambda pair: str(pair[0]))
        ],
        "household_profile_count": len(s._household_profiles),
        "household_profiles": {user: dict(row) for user, row in sorted(s._household_profiles.items())},
    }


def voice_attention_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    default_choreography = {
        "phase": "idle",
        "label": "idle_reset",
        "turn_lean": 0.0,
        "turn_tilt": 0.0,
        "turn_glance_yaw": 0.0,
        "updated_at": 0.0,
    }
    default_stt_diagnostics = {
        "source": "none",
        "fallback_used": False,
        "confidence_score": 0.0,
        "confidence_band": "unknown",
        "avg_logprob": -3.0,
        "avg_no_speech_prob": 1.0,
        "language": "unknown",
        "language_probability": 0.0,
        "segment_count": 0,
        "word_count": 0,
        "char_count": 0,
        "updated_at": 0.0,
        "error": "",
    }
    default_acoustic_scene = {
        "last_doa_angle": None,
        "last_doa_speech": None,
        "last_doa_age_sec": 0.0,
        "attention_confidence": 0.0,
        "attention_source": "unknown",
    }
    default_preference_learning = {
        "user": "",
        "updates": {},
        "applied_at": 0.0,
        "source_text": "",
    }
    default_multimodal_grounding = {
        "overall_confidence": 0.0,
        "confidence_band": "low",
        "attention_source": "unknown",
        "modality_scores": {"presence": 0.0, "stt": 0.0, "source": 0.0, "doa": 0.0},
        "signals": {
            "face_recent": False,
            "hand_recent": False,
            "doa_recent": False,
            "doa_speech": None,
            "stt_band": "unknown",
        },
        "reasons": ["unknown"],
    }
    if not s._runtime_voice_state:
        return {
            "mode": "unknown",
            "followup_active": False,
            "sleeping": False,
            "active_room": "unknown",
            "silence_timeout_sec": 0.0,
            "adaptive_silence_timeout_sec": 0.0,
            "speech_rate_wps": 0.0,
            "interruption_likelihood": 0.0,
            "turn_choreography": default_choreography,
            "stt_diagnostics": default_stt_diagnostics,
            "voice_profile_user": "unknown",
            "voice_profile": {"verbosity": "normal", "confirmations": "standard", "pace": "normal", "tone": "auto"},
            "voice_profile_count": 0,
            "acoustic_scene": default_acoustic_scene,
            "preference_learning": default_preference_learning,
            "multimodal_grounding": default_multimodal_grounding,
        }
    snapshot = {str(key): value for key, value in s._runtime_voice_state.items()}
    snapshot.setdefault("silence_timeout_sec", 0.0)
    snapshot.setdefault("adaptive_silence_timeout_sec", float(snapshot.get("silence_timeout_sec", 0.0) or 0.0))
    snapshot.setdefault("speech_rate_wps", 0.0)
    snapshot.setdefault("interruption_likelihood", 0.0)
    if not isinstance(snapshot.get("turn_choreography"), dict):
        snapshot["turn_choreography"] = default_choreography
    if not isinstance(snapshot.get("stt_diagnostics"), dict):
        snapshot["stt_diagnostics"] = default_stt_diagnostics
    else:
        stt_diag = {str(key): value for key, value in snapshot["stt_diagnostics"].items()}
        for key, value in default_stt_diagnostics.items():
            stt_diag.setdefault(key, value)
        snapshot["stt_diagnostics"] = stt_diag
    snapshot.setdefault("voice_profile_user", "unknown")
    if not isinstance(snapshot.get("voice_profile"), dict):
        snapshot["voice_profile"] = {
            "verbosity": "normal",
            "confirmations": "standard",
            "pace": "normal",
            "tone": "auto",
        }
    else:
        profile = {str(key): value for key, value in snapshot["voice_profile"].items()}
        profile.setdefault("verbosity", "normal")
        profile.setdefault("confirmations", "standard")
        profile.setdefault("pace", "normal")
        profile.setdefault("tone", "auto")
        snapshot["voice_profile"] = profile
    snapshot.setdefault("voice_profile_count", 0)
    if not isinstance(snapshot.get("acoustic_scene"), dict):
        snapshot["acoustic_scene"] = default_acoustic_scene
    else:
        acoustic_scene = {
            str(key): value for key, value in snapshot["acoustic_scene"].items()
        }
        for key, value in default_acoustic_scene.items():
            acoustic_scene.setdefault(key, value)
        snapshot["acoustic_scene"] = acoustic_scene
    if not isinstance(snapshot.get("preference_learning"), dict):
        snapshot["preference_learning"] = default_preference_learning
    else:
        preference_learning = {
            str(key): value
            for key, value in snapshot["preference_learning"].items()
        }
        for key, value in default_preference_learning.items():
            preference_learning.setdefault(key, value)
        if not isinstance(preference_learning.get("updates"), dict):
            preference_learning["updates"] = {}
        snapshot["preference_learning"] = preference_learning
    if not isinstance(snapshot.get("multimodal_grounding"), dict):
        snapshot["multimodal_grounding"] = default_multimodal_grounding
    else:
        multimodal_grounding = {
            str(key): value for key, value in snapshot["multimodal_grounding"].items()
        }
        for key, value in default_multimodal_grounding.items():
            multimodal_grounding.setdefault(key, value)
        if not isinstance(multimodal_grounding.get("modality_scores"), dict):
            multimodal_grounding["modality_scores"] = dict(
                default_multimodal_grounding["modality_scores"]
            )
        if not isinstance(multimodal_grounding.get("signals"), dict):
            multimodal_grounding["signals"] = dict(
                default_multimodal_grounding["signals"]
            )
        reasons = multimodal_grounding.get("reasons")
        if not isinstance(reasons, list):
            multimodal_grounding["reasons"] = ["unknown"]
        snapshot["multimodal_grounding"] = multimodal_grounding
    return snapshot


def observability_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    default_intent_metrics = {
        "turn_count": 0.0,
        "answer_intent_count": 0.0,
        "action_intent_count": 0.0,
        "hybrid_intent_count": 0.0,
        "answer_sample_count": 0.0,
        "completion_sample_count": 0.0,
        "answer_quality_success_rate": 0.0,
        "completion_success_rate": 0.0,
        "correction_count": 0.0,
        "correction_frequency": 0.0,
        "preference_update_turns": 0.0,
        "preference_update_fields": 0.0,
    }
    default_multimodal_metrics = {
        "turn_count": 0.0,
        "avg_confidence": 0.0,
        "low_confidence_count": 0.0,
        "low_confidence_rate": 0.0,
    }
    if not s._runtime_observability_state:
        return {
            "enabled": False,
            "uptime_sec": 0.0,
            "restart_count": 0,
            "alerts": [],
            "intent_metrics": default_intent_metrics,
            "multimodal_metrics": default_multimodal_metrics,
            "latency_dashboards": {
                "sample_count": 0,
                "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                "by_intent": {},
                "by_tool_mix": {},
                "by_wake_mode": {},
            },
            "policy_decision_analytics": {
                "decision_count": 0,
                "by_tool": {},
                "by_status": {},
                "by_reason": {},
                "by_user": {},
                "by_user_tool": {},
            },
        }
    snapshot = {str(key): value for key, value in s._runtime_observability_state.items()}
    if not isinstance(snapshot.get("intent_metrics"), dict):
        snapshot["intent_metrics"] = default_intent_metrics
    else:
        intent_metrics = {
            str(key): value for key, value in snapshot["intent_metrics"].items()
        }
        for key, value in default_intent_metrics.items():
            intent_metrics.setdefault(key, value)
        snapshot["intent_metrics"] = intent_metrics
    if not isinstance(snapshot.get("multimodal_metrics"), dict):
        snapshot["multimodal_metrics"] = default_multimodal_metrics
    else:
        multimodal_metrics = {
            str(key): value for key, value in snapshot["multimodal_metrics"].items()
        }
        for key, value in default_multimodal_metrics.items():
            multimodal_metrics.setdefault(key, value)
        snapshot["multimodal_metrics"] = multimodal_metrics
    if not isinstance(snapshot.get("latency_dashboards"), dict):
        snapshot["latency_dashboards"] = {
            "sample_count": 0,
            "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "by_intent": {},
            "by_tool_mix": {},
            "by_wake_mode": {},
        }
    if not isinstance(snapshot.get("policy_decision_analytics"), dict):
        snapshot["policy_decision_analytics"] = {
            "decision_count": 0,
            "by_tool": {},
            "by_status": {},
            "by_reason": {},
            "by_user": {},
            "by_user_tool": {},
        }
    return snapshot


def skills_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    if not s._runtime_skills_state:
        if s._skill_registry is not None:
            return s._skill_registry.status_snapshot()
        return {
            "enabled": False,
            "loaded_count": 0,
            "enabled_count": 0,
            "skills": [],
        }
    return {str(key): value for key, value in s._runtime_skills_state.items()}


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
