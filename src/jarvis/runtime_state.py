"""Runtime state, profile, and invariant helpers for Jarvis main loop."""

from __future__ import annotations

import json
import math
import time
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable


def _parse_voice_profiles(
    runtime: Any,
    raw_profiles: Any,
    *,
    valid_voice_profile_verbosity: set[str],
    valid_voice_profile_confirmations: set[str],
    valid_voice_profile_pace: set[str],
    valid_voice_profile_tone: set[str],
) -> dict[str, dict[str, str]]:
    if not isinstance(raw_profiles, dict):
        return {}
    parsed_profiles: dict[str, dict[str, str]] = {}
    for raw_user, raw_profile in raw_profiles.items():
        user = str(raw_user).strip().lower()
        if not user or not isinstance(raw_profile, dict):
            continue
        profile: dict[str, str] = {}
        verbosity = runtime._parse_control_choice(
            raw_profile.get("verbosity"),
            valid_voice_profile_verbosity,
        )
        confirmations = runtime._parse_control_choice(
            raw_profile.get("confirmations"),
            valid_voice_profile_confirmations,
        )
        pace = runtime._parse_control_choice(
            raw_profile.get("pace"),
            valid_voice_profile_pace,
        )
        tone = runtime._parse_control_choice(
            raw_profile.get("tone"),
            valid_voice_profile_tone,
        )
        if verbosity is not None:
            profile["verbosity"] = verbosity
        if confirmations is not None:
            profile["confirmations"] = confirmations
        if pace is not None:
            profile["pace"] = pace
        if tone is not None:
            profile["tone"] = tone
        if profile:
            parsed_profiles[user] = profile
    return parsed_profiles


def load_runtime_state(
    runtime: Any,
    *,
    episodic_timeline_maxlen: int,
    valid_persona_styles: set[str],
    valid_backchannel_styles: set[str],
    valid_voice_profile_verbosity: set[str],
    valid_voice_profile_confirmations: set[str],
    valid_voice_profile_pace: set[str],
    valid_voice_profile_tone: set[str],
    valid_control_presets: set[str],
    set_safe_mode_fn: Callable[[bool], None],
) -> None:
    path = getattr(runtime, "_runtime_state_path", None)
    if path is None or not isinstance(path, Path):
        return
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    voice = runtime._voice_controller()
    voice_state = payload.get("voice")
    if isinstance(voice_state, dict):
        if "mode" in voice_state:
            voice.set_mode(str(voice_state.get("mode", voice.mode)))
        if "timeout_profile" in voice_state:
            voice.set_timeout_profile(
                str(voice_state.get("timeout_profile", voice.timeout_profile))
            )
        voice.set_push_to_talk_active(
            bool(voice_state.get("push_to_talk_active", False))
        )
        voice.sleeping = bool(voice_state.get("sleeping", False))

    runtime_state = payload.get("runtime")
    if isinstance(runtime_state, dict):
        motion_enabled = runtime._parse_control_bool(runtime_state.get("motion_enabled"))
        if motion_enabled is not None:
            runtime.config.motion_enabled = motion_enabled
        home_enabled = runtime._parse_control_bool(runtime_state.get("home_enabled"))
        if home_enabled is not None:
            runtime.config.home_enabled = home_enabled
        safe_mode_enabled = runtime._parse_control_bool(
            runtime_state.get("safe_mode_enabled")
        )
        if safe_mode_enabled is not None:
            runtime.config.safe_mode_enabled = safe_mode_enabled
        tts_enabled = runtime._parse_control_bool(runtime_state.get("tts_enabled"))
        if tts_enabled is not None:
            runtime._tts_output_enabled = tts_enabled
        persona_style = runtime._parse_control_choice(
            runtime_state.get("persona_style"),
            valid_persona_styles,
        )
        if persona_style is not None:
            runtime._set_persona_style(persona_style)
        backchannel_style = runtime._parse_control_choice(
            runtime_state.get("backchannel_style"),
            valid_backchannel_styles,
        )
        if backchannel_style is not None:
            runtime.config.backchannel_style = backchannel_style
            runtime.presence.set_backchannel_style(backchannel_style)

        parsed_profiles = _parse_voice_profiles(
            runtime,
            runtime_state.get("voice_user_profiles"),
            valid_voice_profile_verbosity=valid_voice_profile_verbosity,
            valid_voice_profile_confirmations=valid_voice_profile_confirmations,
            valid_voice_profile_pace=valid_voice_profile_pace,
            valid_voice_profile_tone=valid_voice_profile_tone,
        )
        if parsed_profiles:
            runtime._voice_user_profiles = parsed_profiles

        preset = str(
            runtime_state.get("active_control_preset", "custom")
        ).strip().lower()
        runtime._active_control_preset = (
            preset if preset in valid_control_presets else "custom"
        )

    set_safe_mode_fn(bool(getattr(runtime.config, "safe_mode_enabled", False)))
    runtime._awaiting_confirmation = bool(payload.get("awaiting_confirmation", False))
    pending = payload.get("pending_text")
    runtime._pending_text = str(pending) if isinstance(pending, str) else None
    runtime._awaiting_repair_confirmation = bool(
        payload.get("awaiting_repair_confirmation", False)
    )
    repair_pending = payload.get("repair_candidate_text")
    runtime._repair_candidate_text = (
        str(repair_pending) if isinstance(repair_pending, str) else None
    )
    if not runtime._awaiting_repair_confirmation:
        runtime._repair_candidate_text = None
    elif not runtime._repair_candidate_text:
        runtime._awaiting_repair_confirmation = False

    raw_timeline = payload.get("episodic_timeline")
    parsed_timeline: list[dict[str, Any]] = []

    def safe_int(value: Any, default: int = 0) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return default
        return number

    def safe_float(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return number

    if isinstance(raw_timeline, list):
        for item in raw_timeline[:episodic_timeline_maxlen]:
            if not isinstance(item, dict):
                continue
            snapshot = {
                "episode_id": safe_int(item.get("episode_id", 0), 0),
                "timestamp": safe_float(item.get("timestamp", 0.0), 0.0),
                "turn_id": safe_int(item.get("turn_id", 0), 0),
                "intent": str(item.get("intent", "unknown")),
                "lifecycle": str(item.get("lifecycle", "unknown")),
                "summary": str(item.get("summary", "")).strip()[:240],
                "tool_count": max(0, safe_int(item.get("tool_count", 0), 0)),
                "completion_success": item.get("completion_success"),
                "response_success": item.get("response_success"),
            }
            if (
                snapshot["episode_id"] <= 0
                or snapshot["timestamp"] <= 0.0
                or not snapshot["summary"]
            ):
                continue
            parsed_timeline.append(snapshot)
    runtime._episodic_timeline = deque(parsed_timeline, maxlen=episodic_timeline_maxlen)
    try:
        loaded_episode_seq = int(payload.get("episodic_timeline_seq", 0) or 0)
    except (TypeError, ValueError):
        loaded_episode_seq = 0
    runtime._episode_seq = max(loaded_episode_seq, len(parsed_timeline))


def save_runtime_state(
    runtime: Any,
    *,
    episodic_timeline_maxlen: int,
    valid_persona_styles: set[str],
    valid_backchannel_styles: set[str],
) -> None:
    path = getattr(runtime, "_runtime_state_path", None)
    if path is None or not isinstance(path, Path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    voice = runtime._voice_controller()

    preview_snapshot = getattr(runtime, "_personality_preview_snapshot", None)
    if isinstance(preview_snapshot, dict):
        persisted_persona_style = runtime._parse_control_choice(
            preview_snapshot.get("persona_style"),
            valid_persona_styles,
        ) or str(getattr(runtime.config, "persona_style", "composed"))
        persisted_backchannel_style = runtime._parse_control_choice(
            preview_snapshot.get("backchannel_style"),
            valid_backchannel_styles,
        ) or str(getattr(runtime.config, "backchannel_style", "balanced"))
    else:
        persisted_persona_style = str(
            getattr(runtime.config, "persona_style", "composed")
        )
        persisted_backchannel_style = str(
            getattr(runtime.config, "backchannel_style", "balanced")
        )

    payload = {
        "saved_at": time.time(),
        "voice": {
            "mode": voice.mode,
            "timeout_profile": voice.timeout_profile,
            "push_to_talk_active": voice.push_to_talk_active,
            "sleeping": voice.sleeping,
        },
        "runtime": {
            "motion_enabled": bool(runtime.config.motion_enabled),
            "home_enabled": bool(runtime.config.home_enabled),
            "safe_mode_enabled": bool(
                getattr(runtime.config, "safe_mode_enabled", False)
            ),
            "tts_enabled": bool(getattr(runtime, "_tts_output_enabled", True)),
            "persona_style": persisted_persona_style,
            "backchannel_style": persisted_backchannel_style,
            "voice_user_profiles": getattr(runtime, "_voice_user_profiles", {}),
            "active_control_preset": str(
                getattr(runtime, "_active_control_preset", "custom")
            ),
        },
        "awaiting_confirmation": bool(
            getattr(runtime, "_awaiting_confirmation", False)
        ),
        "pending_text": getattr(runtime, "_pending_text", None),
        "awaiting_repair_confirmation": bool(
            getattr(runtime, "_awaiting_repair_confirmation", False)
        ),
        "repair_candidate_text": getattr(runtime, "_repair_candidate_text", None),
        "episodic_timeline_seq": int(getattr(runtime, "_episode_seq", 0)),
        "episodic_timeline": list(getattr(runtime, "_episodic_timeline", []))[
            :episodic_timeline_maxlen
        ],
    }
    with suppress(OSError):
        path.write_text(json.dumps(payload, indent=2))


def runtime_invariant_snapshot(runtime: Any, *, recent_limit: int = 20) -> dict[str, Any]:
    recent = list(getattr(runtime, "_runtime_invariant_recent", []))
    return {
        "last_checked_at": float(getattr(runtime, "_runtime_invariant_checked_at", 0.0)),
        "total_violations": int(
            getattr(runtime, "_runtime_invariant_violations_total", 0)
        ),
        "total_auto_heals": int(
            getattr(runtime, "_runtime_invariant_auto_heals_total", 0)
        ),
        "recent": recent[:recent_limit],
    }


def check_runtime_invariants(
    runtime: Any,
    *,
    auto_heal: bool,
    runtime_invariant_history_maxlen: int,
    valid_control_presets: set[str],
) -> dict[str, Any]:
    now = time.time()
    runtime._runtime_invariant_checked_at = now
    runtime._runtime_invariant_checked_monotonic = time.monotonic()
    voice = runtime._voice_controller()
    violations: list[dict[str, Any]] = []
    mode = str(getattr(voice, "mode", "unknown")).strip().lower()
    push_to_talk_active = bool(getattr(voice, "push_to_talk_active", False))

    if mode == "push_to_talk" and not push_to_talk_active:
        healed = False
        if auto_heal:
            voice.set_push_to_talk_active(True)
            healed = True
        violations.append(
            {
                "code": "push_to_talk_mode_inactive",
                "message": "wake mode push_to_talk requires push_to_talk_active=true",
                "healed": healed,
            }
        )
    if mode != "push_to_talk" and push_to_talk_active:
        healed = False
        if auto_heal:
            voice.set_push_to_talk_active(False)
            healed = True
        violations.append(
            {
                "code": "push_to_talk_active_mode_mismatch",
                "message": "push_to_talk_active=true requires wake mode push_to_talk",
                "healed": healed,
            }
        )

    preset = str(getattr(runtime, "_active_control_preset", "custom")).strip().lower()
    if preset not in valid_control_presets and preset != "custom":
        healed = False
        if auto_heal:
            runtime._active_control_preset = "custom"
            healed = True
        violations.append(
            {
                "code": "invalid_control_preset",
                "message": "active control preset must be known or custom",
                "healed": healed,
            }
        )

    recent = getattr(runtime, "_runtime_invariant_recent", None)
    if not isinstance(recent, deque):
        recent = deque(maxlen=runtime_invariant_history_maxlen)
        runtime._runtime_invariant_recent = recent
    if not hasattr(runtime, "_runtime_invariant_violations_total"):
        runtime._runtime_invariant_violations_total = 0
    if not hasattr(runtime, "_runtime_invariant_auto_heals_total"):
        runtime._runtime_invariant_auto_heals_total = 0

    healed_any = False
    for item in violations:
        healed = bool(item.get("healed", False))
        if healed:
            healed_any = True
        runtime._runtime_invariant_violations_total += 1
        if healed:
            runtime._runtime_invariant_auto_heals_total += 1
        record = {
            "timestamp": now,
            "code": str(item.get("code", "unknown")),
            "message": str(item.get("message", "")),
            "healed": healed,
        }
        recent.appendleft(record)
        observability = getattr(runtime, "_observability", None)
        if observability is not None:
            with suppress(Exception):
                observability.record_event("runtime_invariant", record)

    if healed_any:
        runtime._persist_runtime_state_safe()

    return runtime_invariant_snapshot(runtime)


def runtime_profile_snapshot(runtime: Any) -> dict[str, Any]:
    voice = runtime._voice_controller()
    return {
        "wake_mode": str(getattr(voice, "mode", "wake_word")),
        "sleeping": bool(getattr(voice, "sleeping", False)),
        "timeout_profile": str(getattr(voice, "timeout_profile", "normal")),
        "push_to_talk_active": bool(getattr(voice, "push_to_talk_active", False)),
        "motion_enabled": bool(getattr(runtime.config, "motion_enabled", False)),
        "home_enabled": bool(getattr(runtime.config, "home_enabled", False)),
        "safe_mode_enabled": bool(getattr(runtime.config, "safe_mode_enabled", False)),
        "tts_enabled": bool(getattr(runtime, "_tts_output_enabled", True)),
        "persona_style": str(getattr(runtime.config, "persona_style", "composed")),
        "backchannel_style": str(
            getattr(runtime.config, "backchannel_style", "balanced")
        ),
        "voice_user_profiles": {
            str(name): dict(profile)
            for name, profile in getattr(runtime, "_voice_user_profiles", {}).items()
            if isinstance(profile, dict)
        },
        "active_control_preset": str(getattr(runtime, "_active_control_preset", "custom")),
    }


def apply_runtime_profile(
    runtime: Any,
    profile: dict[str, Any],
    *,
    mark_custom: bool,
    valid_wake_modes: set[str],
    valid_timeout_profiles: set[str],
    valid_persona_styles: set[str],
    valid_backchannel_styles: set[str],
    valid_voice_profile_verbosity: set[str],
    valid_voice_profile_confirmations: set[str],
    valid_voice_profile_pace: set[str],
    valid_voice_profile_tone: set[str],
    set_safe_mode_fn: Callable[[bool], None],
) -> dict[str, Any]:
    voice = runtime._voice_controller()
    wake_mode = runtime._parse_control_choice(profile.get("wake_mode"), valid_wake_modes)
    if wake_mode is not None:
        voice.set_mode(wake_mode)

    sleeping = runtime._parse_control_bool(profile.get("sleeping"))
    if sleeping is not None:
        voice.sleeping = sleeping
        if not sleeping:
            voice.continue_listening()

    timeout_profile = runtime._parse_control_choice(
        profile.get("timeout_profile"),
        valid_timeout_profiles,
    )
    if timeout_profile is not None:
        voice.set_timeout_profile(timeout_profile)

    push_to_talk = runtime._parse_control_bool(profile.get("push_to_talk_active"))
    if push_to_talk is not None:
        voice.set_push_to_talk_active(push_to_talk)

    motion_enabled = runtime._parse_control_bool(profile.get("motion_enabled"))
    if motion_enabled is not None:
        runtime.config.motion_enabled = motion_enabled
        if motion_enabled:
            with suppress(Exception):
                runtime.presence.start()
        else:
            with suppress(Exception):
                runtime.presence.stop()

    home_enabled = runtime._parse_control_bool(profile.get("home_enabled"))
    if home_enabled is not None:
        runtime.config.home_enabled = home_enabled

    safe_mode_enabled = runtime._parse_control_bool(profile.get("safe_mode_enabled"))
    if safe_mode_enabled is not None:
        runtime.config.safe_mode_enabled = safe_mode_enabled
        set_safe_mode_fn(safe_mode_enabled)

    tts_enabled = runtime._parse_control_bool(profile.get("tts_enabled"))
    if tts_enabled is not None:
        runtime._tts_output_enabled = tts_enabled

    persona_style = runtime._parse_control_choice(
        profile.get("persona_style"),
        valid_persona_styles,
    )
    if persona_style is not None:
        runtime._set_persona_style(persona_style)

    backchannel_style = runtime._parse_control_choice(
        profile.get("backchannel_style"),
        valid_backchannel_styles,
    )
    if backchannel_style is not None:
        runtime.config.backchannel_style = backchannel_style
        runtime.presence.set_backchannel_style(backchannel_style)

    raw_profiles = profile.get("voice_user_profiles")
    if isinstance(raw_profiles, dict):
        runtime._voice_user_profiles = _parse_voice_profiles(
            runtime,
            raw_profiles,
            valid_voice_profile_verbosity=valid_voice_profile_verbosity,
            valid_voice_profile_confirmations=valid_voice_profile_confirmations,
            valid_voice_profile_pace=valid_voice_profile_pace,
            valid_voice_profile_tone=valid_voice_profile_tone,
        )

    if mark_custom:
        runtime._active_control_preset = "custom"
    runtime._publish_voice_status()
    runtime._persist_runtime_state_safe()
    return runtime_profile_snapshot(runtime)


def preset_profile(runtime: Any, preset: str) -> dict[str, Any]:
    name = str(preset or "").strip().lower()
    if name == "quiet_hours":
        return {
            "wake_mode": "wake_word",
            "sleeping": False,
            "timeout_profile": "short",
            "push_to_talk_active": False,
            "motion_enabled": bool(getattr(runtime.config, "motion_enabled", False)),
            "home_enabled": False,
            "safe_mode_enabled": True,
            "tts_enabled": True,
            "persona_style": "composed",
            "backchannel_style": "quiet",
        }
    if name == "demo_mode":
        return {
            "wake_mode": "always_listening",
            "sleeping": False,
            "timeout_profile": "long",
            "push_to_talk_active": False,
            "motion_enabled": True,
            "home_enabled": False,
            "safe_mode_enabled": True,
            "tts_enabled": True,
            "persona_style": "jarvis",
            "backchannel_style": "expressive",
        }
    if name == "maintenance_mode":
        return {
            "wake_mode": "push_to_talk",
            "sleeping": True,
            "timeout_profile": "short",
            "push_to_talk_active": True,
            "motion_enabled": False,
            "home_enabled": False,
            "safe_mode_enabled": True,
            "tts_enabled": False,
            "persona_style": "terse",
            "backchannel_style": "quiet",
        }
    return {}


def apply_control_preset(
    runtime: Any,
    preset: str,
    *,
    valid_control_presets: set[str],
) -> dict[str, Any] | None:
    name = str(preset or "").strip().lower()
    if name not in valid_control_presets:
        return None
    profile = preset_profile(runtime, name)
    applied = runtime._apply_runtime_profile(profile, mark_custom=False)
    runtime._active_control_preset = name
    runtime._publish_voice_status()
    runtime._persist_runtime_state_safe()
    return applied
