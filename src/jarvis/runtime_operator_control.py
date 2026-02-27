"""Operator control action dispatcher for the Jarvis runtime."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from jarvis.runtime_constants import (
    VALID_BACKCHANNEL_STYLES,
    VALID_CONTROL_PRESETS,
    VALID_PERSONA_STYLES,
    VALID_VOICE_PROFILE_CONFIRMATIONS,
    VALID_VOICE_PROFILE_PACE,
    VALID_VOICE_PROFILE_TONE,
    VALID_VOICE_PROFILE_VERBOSITY,
)
from jarvis.tools import services as service_tools
from jarvis.voice_attention import VALID_TIMEOUT_PROFILES, VALID_WAKE_MODES


async def handle_operator_control(runtime: Any, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    voice = runtime._voice_controller()
    command = str(action or "").strip().lower()
    data = payload if isinstance(payload, dict) else {}
    if not command:
        return {
            "ok": False,
            "error": "invalid_action",
            "message": "action is required",
            "available_actions": runtime._operator_available_actions(),
        }
    if command == "set_wake_mode":
        mode = runtime._parse_control_choice(data.get("mode"), VALID_WAKE_MODES)
        if mode is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "mode",
                "expected": sorted(VALID_WAKE_MODES),
            }
        mode = voice.set_mode(mode)
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "mode": mode}
    if command == "set_sleeping":
        sleeping = runtime._parse_control_bool(data.get("sleeping"))
        if sleeping is None:
            return {"ok": False, "error": "invalid_payload", "field": "sleeping", "expected": "boolean"}
        voice.sleeping = sleeping
        if not sleeping:
            voice.continue_listening()
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "sleeping": voice.sleeping}
    if command == "set_timeout_profile":
        profile = runtime._parse_control_choice(data.get("profile"), VALID_TIMEOUT_PROFILES)
        if profile is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "profile",
                "expected": sorted(VALID_TIMEOUT_PROFILES),
            }
        profile = voice.set_timeout_profile(profile)
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "timeout_profile": profile}
    if command == "set_push_to_talk":
        active = runtime._parse_control_bool(data.get("active"))
        if active is None:
            return {"ok": False, "error": "invalid_payload", "field": "active", "expected": "boolean"}
        voice.set_push_to_talk_active(active)
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "push_to_talk_active": active}
    if command == "set_motion_enabled":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime.config.motion_enabled = enabled
        if enabled:
            with suppress(Exception):
                runtime.presence.start()
        else:
            with suppress(Exception):
                runtime.presence.stop()
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "motion_enabled": enabled}
    if command == "set_home_enabled":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime.config.home_enabled = enabled
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "home_enabled": enabled}
    if command == "set_safe_mode":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime.config.safe_mode_enabled = enabled
        service_tools.set_safe_mode(enabled)
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "safe_mode_enabled": enabled}
    if command == "set_tts_enabled":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime._tts_output_enabled = enabled
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "tts_enabled": enabled}
    if command == "set_persona_style":
        style = runtime._parse_control_choice(data.get("style"), VALID_PERSONA_STYLES)
        if style is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "style",
                "expected": sorted(VALID_PERSONA_STYLES),
            }
        runtime._set_persona_style(style)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "persona_style": style}
    if command == "set_backchannel_style":
        style = runtime._parse_control_choice(data.get("style"), VALID_BACKCHANNEL_STYLES)
        if style is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "style",
                "expected": sorted(VALID_BACKCHANNEL_STYLES),
            }
        runtime.config.backchannel_style = style
        runtime.presence.set_backchannel_style(style)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "backchannel_style": style}
    if command == "set_voice_profile":
        user = str(data.get("user", "")).strip().lower()
        if not user:
            return {"ok": False, "error": "invalid_payload", "field": "user", "expected": "non-empty string"}
        verbosity = runtime._parse_control_choice(data.get("verbosity"), VALID_VOICE_PROFILE_VERBOSITY)
        confirmations = runtime._parse_control_choice(data.get("confirmations"), VALID_VOICE_PROFILE_CONFIRMATIONS)
        pace = runtime._parse_control_choice(data.get("pace"), VALID_VOICE_PROFILE_PACE)
        tone = runtime._parse_control_choice(data.get("tone"), VALID_VOICE_PROFILE_TONE)
        profile_patch: dict[str, str] = {}
        if "verbosity" in data:
            if verbosity is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "verbosity",
                    "expected": sorted(VALID_VOICE_PROFILE_VERBOSITY),
                }
            profile_patch["verbosity"] = verbosity
        if "confirmations" in data:
            if confirmations is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "confirmations",
                    "expected": sorted(VALID_VOICE_PROFILE_CONFIRMATIONS),
                }
            profile_patch["confirmations"] = confirmations
        if "pace" in data:
            if pace is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "pace",
                    "expected": sorted(VALID_VOICE_PROFILE_PACE),
                }
            profile_patch["pace"] = pace
        if "tone" in data:
            if tone is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "tone",
                    "expected": sorted(VALID_VOICE_PROFILE_TONE),
                }
            profile_patch["tone"] = tone
        if not profile_patch:
            return {
                "ok": False,
                "error": "invalid_payload",
                "message": "provide at least one of verbosity, confirmations, pace, or tone",
            }
        profiles = getattr(runtime, "_voice_user_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        entry = profiles.get(user, {})
        if not isinstance(entry, dict):
            entry = {}
        merged = {**entry, **profile_patch}
        profiles[user] = merged
        runtime._voice_user_profiles = profiles
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        runtime._publish_voice_status()
        return {"ok": True, "user": user, "profile": merged}
    if command == "clear_voice_profile":
        user = str(data.get("user", "")).strip().lower()
        if not user:
            return {"ok": False, "error": "invalid_payload", "field": "user", "expected": "non-empty string"}
        profiles = getattr(runtime, "_voice_user_profiles", {})
        removed = False
        if isinstance(profiles, dict) and user in profiles:
            profiles.pop(user, None)
            removed = True
        runtime._voice_user_profiles = profiles if isinstance(profiles, dict) else {}
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        runtime._publish_voice_status()
        return {"ok": True, "user": user, "removed": removed}
    if command == "list_voice_profiles":
        profiles = getattr(runtime, "_voice_user_profiles", {})
        snapshot = {
            str(name): dict(value)
            for name, value in profiles.items()
            if isinstance(value, dict)
        } if isinstance(profiles, dict) else {}
        active_user = runtime._active_voice_user()
        return {
            "ok": True,
            "active_user": active_user,
            "active_profile": runtime._active_voice_profile(user=active_user),
            "profiles": snapshot,
        }
    if command == "apply_control_preset":
        preset = runtime._parse_control_choice(data.get("preset"), VALID_CONTROL_PRESETS)
        if preset is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "preset",
                "expected": sorted(VALID_CONTROL_PRESETS),
            }
        applied = runtime._apply_control_preset(preset)
        if applied is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "preset",
                "expected": sorted(VALID_CONTROL_PRESETS),
            }
        return {"ok": True, "preset": preset, "runtime_profile": applied}
    if command == "export_runtime_profile":
        return {"ok": True, "runtime_profile": runtime._runtime_profile_snapshot()}
    if command == "import_runtime_profile":
        profile = data.get("profile")
        if not isinstance(profile, dict):
            return {"ok": False, "error": "invalid_payload", "field": "profile", "expected": "object"}
        applied = runtime._apply_runtime_profile(profile, mark_custom=True)
        return {"ok": True, "runtime_profile": applied}
    if command == "preview_personality":
        persona_style = runtime._parse_control_choice(data.get("persona_style"), VALID_PERSONA_STYLES)
        backchannel_style = runtime._parse_control_choice(data.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
        if persona_style is None and backchannel_style is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "message": "provide persona_style and/or backchannel_style",
                "expected": {
                    "persona_style": sorted(VALID_PERSONA_STYLES),
                    "backchannel_style": sorted(VALID_BACKCHANNEL_STYLES),
                },
            }
        if getattr(runtime, "_personality_preview_snapshot", None) is None:
            runtime._personality_preview_snapshot = {
                "persona_style": str(getattr(runtime.config, "persona_style", "composed")),
                "backchannel_style": str(getattr(runtime.config, "backchannel_style", "balanced")),
            }
        if persona_style is not None:
            runtime._set_persona_style(persona_style)
        if backchannel_style is not None:
            runtime.config.backchannel_style = backchannel_style
            runtime.presence.set_backchannel_style(backchannel_style)
        runtime._active_control_preset = "custom"
        return {
            "ok": True,
            "preview_active": True,
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
            "baseline": dict(runtime._personality_preview_snapshot or {}),
        }
    if command == "commit_personality_preview":
        was_active = isinstance(getattr(runtime, "_personality_preview_snapshot", None), dict)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {
            "ok": True,
            "committed": was_active,
            "preview_active": False,
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
        }
    if command == "rollback_personality_preview":
        snapshot = getattr(runtime, "_personality_preview_snapshot", None)
        if not isinstance(snapshot, dict):
            return {
                "ok": True,
                "rolled_back": False,
                "preview_active": False,
                "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
                "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
            }
        persona_style = runtime._parse_control_choice(snapshot.get("persona_style"), VALID_PERSONA_STYLES)
        backchannel_style = runtime._parse_control_choice(snapshot.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
        if persona_style is not None:
            runtime._set_persona_style(persona_style)
        if backchannel_style is not None:
            runtime.config.backchannel_style = backchannel_style
            runtime.presence.set_backchannel_style(backchannel_style)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        return {
            "ok": True,
            "rolled_back": True,
            "preview_active": False,
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
        }
    if command == "clear_inbound_webhooks":
        result = await service_tools.webhook_inbound_clear({})
        text = result.get("content", [{}])[0].get("text", "")
        return {"ok": True, "message": text}
    if command == "skills_reload":
        runtime._skills.discover()
        runtime._publish_skills_status()
        return {"ok": True, "skills": runtime._skills.status_snapshot()}
    if command == "skills_enable":
        name = str(data.get("name", "")).strip().lower()
        if not name:
            return {"ok": False, "error": "invalid_payload", "field": "name", "expected": "non-empty string"}
        ok, detail = runtime._skills.enable_skill(name)
        runtime._publish_skills_status()
        return {"ok": ok, "detail": detail, "name": name}
    if command == "skills_disable":
        name = str(data.get("name", "")).strip().lower()
        if not name:
            return {"ok": False, "error": "invalid_payload", "field": "name", "expected": "non-empty string"}
        ok, detail = runtime._skills.disable_skill(name)
        runtime._publish_skills_status()
        return {"ok": ok, "detail": detail, "name": name}
    return {
        "ok": False,
        "error": "invalid_action",
        "message": "unknown action",
        "available_actions": runtime._operator_available_actions(),
    }
