"""Runtime helpers for governance/status payload assembly."""

from __future__ import annotations

from typing import Any

def tool_policy_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    cfg = s._config
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
        "memory_ingestion_min_confidence": float(getattr(cfg, "memory_ingestion_min_confidence", 0.0) if cfg else 0.0),
        "memory_ingest_async_enabled": bool(getattr(cfg, "memory_ingest_async_enabled", False) if cfg else False),
        "identity_enforcement_enabled": s._identity_enforcement_enabled,
        "identity_default_profile": s._identity_default_profile,
        "identity_require_approval": s._identity_require_approval,
        "plan_preview_require_ack": s._plan_preview_require_ack,
        "policy_engine_version": str(s._policy_engine.get("version", "unknown")),
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
