"""Startup and operator-schema helper functions for Jarvis runtime."""

from __future__ import annotations

from typing import Any


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
