"""Startup and operator-schema helper functions for Jarvis runtime."""

from __future__ import annotations

from typing import Any, Callable


def operator_control_schema(
    *,
    valid_wake_modes: set[str],
    valid_timeout_profiles: set[str],
    valid_persona_styles: set[str],
    valid_backchannel_styles: set[str],
    valid_voice_profile_verbosity: set[str],
    valid_voice_profile_confirmations: set[str],
    valid_voice_profile_pace: set[str],
    valid_voice_profile_tone: set[str],
    valid_control_presets: set[str],
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "actions": {
            "set_wake_mode": {
                "required": ["mode"],
                "enum": {"mode": sorted(valid_wake_modes)},
            },
            "set_sleeping": {"required": ["sleeping"], "types": {"sleeping": "boolean"}},
            "set_timeout_profile": {
                "required": ["profile"],
                "enum": {"profile": sorted(valid_timeout_profiles)},
            },
            "set_push_to_talk": {"required": ["active"], "types": {"active": "boolean"}},
            "set_motion_enabled": {"required": ["enabled"], "types": {"enabled": "boolean"}},
            "set_home_enabled": {"required": ["enabled"], "types": {"enabled": "boolean"}},
            "set_safe_mode": {"required": ["enabled"], "types": {"enabled": "boolean"}},
            "set_tts_enabled": {"required": ["enabled"], "types": {"enabled": "boolean"}},
            "set_persona_style": {
                "required": ["style"],
                "enum": {"style": sorted(valid_persona_styles)},
            },
            "set_backchannel_style": {
                "required": ["style"],
                "enum": {"style": sorted(valid_backchannel_styles)},
            },
            "preview_personality": {
                "required": [],
                "enum": {
                    "persona_style": sorted(valid_persona_styles),
                    "backchannel_style": sorted(valid_backchannel_styles),
                },
            },
            "commit_personality_preview": {"required": []},
            "rollback_personality_preview": {"required": []},
            "set_voice_profile": {
                "required": ["user"],
                "types": {"user": "string"},
                "enum": {
                    "verbosity": sorted(valid_voice_profile_verbosity),
                    "confirmations": sorted(valid_voice_profile_confirmations),
                    "pace": sorted(valid_voice_profile_pace),
                    "tone": sorted(valid_voice_profile_tone),
                },
            },
            "clear_voice_profile": {
                "required": ["user"],
                "types": {"user": "string"},
            },
            "list_voice_profiles": {"required": []},
            "apply_control_preset": {
                "required": ["preset"],
                "enum": {"preset": sorted(valid_control_presets)},
            },
            "export_runtime_profile": {"required": []},
            "import_runtime_profile": {
                "required": ["profile"],
                "types": {"profile": "object"},
            },
            "skills_reload": {"required": []},
            "skills_enable": {"required": ["name"], "types": {"name": "string"}},
            "skills_disable": {"required": ["name"], "types": {"name": "string"}},
            "clear_inbound_webhooks": {"required": []},
            "list_pending_approvals": {"required": []},
            "resolve_approval": {
                "required": ["approval_id", "approved"],
                "types": {
                    "approval_id": "string",
                    "approved": "boolean",
                    "notes": "string",
                    "resolver_id": "string",
                    "execute": "boolean",
                },
            },
            "dead_letter_status": {
                "required": [],
                "types": {"limit": "integer", "status_filter": "string"},
            },
            "dead_letter_replay": {
                "required": [],
                "types": {"limit": "integer", "status_filter": "string", "dry_run": "boolean"},
            },
            "list_autonomy_replans": {
                "required": [],
                "types": {"limit": "integer"},
            },
            "apply_autonomy_replan": {
                "required": ["task_id"],
                "types": {
                    "task_id": "string",
                    "draft_id": "string",
                    "plan_steps": "array",
                    "step_contracts": "array",
                    "reset_progress": "boolean",
                    "execute_at": "number",
                    "notes": "string",
                    "resolver_id": "string",
                },
            },
            "copilot_actions": {"required": []},
            "copilot_execute": {
                "required": ["action_id"],
                "types": {"action_id": "string", "payload": "object"},
            },
        },
    }


def startup_blockers(
    *,
    config: Any,
    args: Any,
    valid_operator_auth_modes: set[str],
) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(config, "startup_strict", False)):
        return blockers

    if not bool(getattr(args, "no_tts", False)) and not str(
        getattr(config, "elevenlabs_api_key", "")
    ):
        blockers.append(
            "STARTUP_STRICT: ELEVENLABS_API_KEY is required when TTS is enabled."
        )

    if bool(getattr(config, "operator_server_enabled", False)) and not str(
        getattr(config, "operator_server_host", "")
    ).strip():
        blockers.append("STARTUP_STRICT: OPERATOR_SERVER_HOST cannot be empty.")

    operator_host = str(getattr(config, "operator_server_host", "")).strip().lower()
    operator_auth_mode = str(getattr(config, "operator_auth_mode", "token")).strip().lower()
    if operator_auth_mode not in valid_operator_auth_modes:
        operator_auth_mode = "token"
    operator_token = str(getattr(config, "operator_auth_token", "")).strip()

    if (
        bool(getattr(config, "operator_server_enabled", False))
        and operator_auth_mode in {"token", "session"}
        and not operator_token
    ):
        blockers.append(
            f"STARTUP_STRICT: OPERATOR_AUTH_MODE={operator_auth_mode} requires OPERATOR_AUTH_TOKEN."
        )

    if (
        bool(getattr(config, "operator_server_enabled", False))
        and operator_auth_mode == "off"
        and operator_host not in {"127.0.0.1", "localhost", "::1"}
    ):
        blockers.append(
            "STARTUP_STRICT: OPERATOR_AUTH_MODE=off is not allowed on non-loopback OPERATOR_SERVER_HOST."
        )

    if bool(getattr(config, "skills_require_signature", False)) and not str(
        getattr(config, "skills_signature_key", "")
    ).strip():
        blockers.append(
            "STARTUP_STRICT: SKILLS_SIGNATURE_KEY required when SKILLS_REQUIRE_SIGNATURE=true."
        )

    if (
        bool(getattr(config, "memory_encryption_enabled", False))
        or bool(getattr(config, "audit_encryption_enabled", False))
    ) and not str(getattr(config, "data_encryption_key", "")).strip():
        blockers.append(
            "STARTUP_STRICT: JARVIS_DATA_KEY required when encryption is enabled."
        )

    if bool(getattr(config, "webhook_inbound_enabled", False)) and not str(
        getattr(config, "webhook_inbound_token", "")
        or getattr(config, "webhook_auth_token", "")
    ).strip():
        blockers.append(
            "STARTUP_STRICT: WEBHOOK_INBOUND_ENABLED requires WEBHOOK_INBOUND_TOKEN or WEBHOOK_AUTH_TOKEN."
        )

    return blockers


def startup_summary_lines(
    runtime: Any,
    *,
    normalize_operator_auth_mode_fn: Callable[..., str],
    operator_auth_risk_fn: Callable[..., str],
    valid_operator_auth_modes: set[str],
    tool_service_error_codes: set[str],
    telemetry_service_error_details: set[str],
    telemetry_storage_error_details: set[str],
) -> list[str]:
    tts_enabled = bool(runtime.tts is not None)
    tts_reason = "enabled" if tts_enabled else "disabled (no ELEVENLABS_API_KEY or --no-tts)"
    memory_state = "enabled" if runtime.config.memory_enabled else "disabled"
    warning_count = len(getattr(runtime.config, "startup_warnings", []))
    voice = getattr(runtime, "_voice_attention", None)
    wake_mode = getattr(voice, "mode", "always_listening")
    timeout_profile = getattr(voice, "timeout_profile", "normal")
    skills = getattr(runtime, "_skills", None)
    skills_enabled = bool(skills.enabled) if skills is not None else False
    observability = getattr(runtime, "_observability", None)
    operator_auth_mode = normalize_operator_auth_mode_fn(
        getattr(runtime.config, "operator_auth_mode", "token"),
        valid_modes=valid_operator_auth_modes,
    )
    operator_token_set = bool(str(getattr(runtime.config, "operator_auth_token", "")).strip())
    operator_auth_risk = operator_auth_risk_fn(
        auth_mode=operator_auth_mode,
        token_configured=operator_token_set,
    )
    operator_auth = f"mode={operator_auth_mode} risk={operator_auth_risk}"
    if operator_auth_mode in {"token", "session"}:
        operator_auth = f"{operator_auth} token={'set' if operator_token_set else 'missing'}"
    return [
        f"Mode: {'simulation' if runtime.robot.sim else 'hardware'}",
        f"Motion: {'on' if runtime.config.motion_enabled else 'off'} | Vision: {'on' if not runtime.args.no_vision and not runtime.robot.sim else 'off'} | Hands: {'on' if runtime.config.hand_track_enabled else 'off'}",
        f"Home tools: {'on' if runtime.config.home_enabled else 'off'}",
        f"Safe mode: {'on' if bool(getattr(runtime.config, 'safe_mode_enabled', False)) else 'off'}",
        f"Home conversation: {'on' if runtime.config.home_conversation_enabled else 'off'}",
        f"Wake mode: {wake_mode} | calibration: {getattr(runtime.config, 'wake_calibration_profile', 'default')} | timeout profile: {timeout_profile}",
        f"TTS: {tts_reason}",
        f"Memory: {memory_state} ({runtime.config.memory_path})",
        f"Skills: {'on' if skills_enabled else 'off'} ({getattr(runtime.config, 'skills_dir', 'n/a')})",
        f"Operator server: {'on' if getattr(runtime.config, 'operator_server_enabled', False) else 'off'} ({getattr(runtime.config, 'operator_server_host', '127.0.0.1')}:{getattr(runtime.config, 'operator_server_port', 0)}; {operator_auth})",
        f"Observability: {'on' if observability is not None else 'off'} ({getattr(runtime.config, 'observability_db_path', 'n/a')})",
        f"Persona style: {runtime.config.persona_style}",
        f"Config warnings: {warning_count}",
        f"Tool policy: allow={len(runtime.config.tool_allowlist)} deny={len(runtime.config.tool_denylist)}",
        f"Error taxonomy: total={len(tool_service_error_codes)} service={len(telemetry_service_error_details)} storage={len(telemetry_storage_error_details)}",
    ]
