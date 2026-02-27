"""Voice-status and turn-choreography runtime helpers."""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any, Callable, Mapping


def apply_turn_choreography(
    runtime: Any,
    state: Any,
    *,
    cues_by_state: Mapping[Any, Mapping[str, Any]],
    now_time_fn: Callable[[], float] = time.time,
) -> None:
    cues = cues_by_state.get(state)
    if cues is None:
        return
    label = str(cues.get("label", "unknown"))
    phase = str(state.value)
    current = getattr(runtime, "_turn_choreography", {})
    if isinstance(current, dict) and current.get("phase") == phase and current.get("label") == label:
        return
    signals = getattr(runtime.presence, "signals", None)
    if signals is None:
        return
    turn_lean = float(cues.get("turn_lean", 0.0))
    turn_tilt = float(cues.get("turn_tilt", 0.0))
    turn_glance_yaw = float(cues.get("turn_glance_yaw", 0.0))
    signals.turn_lean = turn_lean
    signals.turn_tilt = turn_tilt
    signals.turn_glance_yaw = turn_glance_yaw
    updated_at = now_time_fn()
    runtime._turn_choreography = {
        "phase": phase,
        "label": label,
        "turn_lean": turn_lean,
        "turn_tilt": turn_tilt,
        "turn_glance_yaw": turn_glance_yaw,
        "updated_at": updated_at,
    }
    observability = getattr(runtime, "_observability", None)
    if observability is not None:
        with suppress(Exception):
            observability.record_event(
                "turn_choreography",
                {
                    "phase": phase,
                    "label": label,
                    "turn_lean": turn_lean,
                    "turn_tilt": turn_tilt,
                    "turn_glance_yaw": turn_glance_yaw,
                },
            )


def turn_choreography_snapshot(runtime: Any, *, idle_state_value: str) -> dict[str, Any]:
    current = getattr(runtime, "_turn_choreography", None)
    if isinstance(current, dict):
        return {str(key): value for key, value in current.items()}
    return {
        "phase": idle_state_value,
        "label": "idle_reset",
        "turn_lean": 0.0,
        "turn_tilt": 0.0,
        "turn_glance_yaw": 0.0,
        "updated_at": 0.0,
    }


def publish_voice_status(
    runtime: Any,
    *,
    set_runtime_voice_state_fn: Callable[[dict[str, Any]], None],
    cues_by_state: Mapping[Any, Mapping[str, Any]],
    idle_state_value: str,
    now_monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    runtime._check_runtime_invariants(auto_heal=True)
    voice = runtime._voice_controller()
    status = voice.status()
    try:
        state = runtime.presence.signals.state
        status["presence_state"] = str(state.value)
        apply_turn_choreography(runtime, state, cues_by_state=cues_by_state)
    except Exception:
        status["presence_state"] = "unknown"
    status["turn_choreography"] = turn_choreography_snapshot(runtime, idle_state_value=idle_state_value)
    status["stt_diagnostics"] = runtime._stt_diagnostics_snapshot()
    status["voice_profile_user"] = runtime._active_voice_user()
    status["voice_profile"] = runtime._active_voice_profile()
    status["voice_profile_count"] = len(getattr(runtime, "_voice_user_profiles", {}))
    status["control_preset"] = str(getattr(runtime, "_active_control_preset", "custom"))
    last_doa_update = float(getattr(runtime, "_last_doa_update", 0.0) or 0.0)
    now_mono = now_monotonic_fn()
    doa_age_sec = 0.0
    if last_doa_update:
        doa_age_sec = max(0.0, now_mono - last_doa_update)
    attention_source = "unknown"
    with suppress(Exception):
        attention_source = str(runtime.presence.attention_source())
    status["acoustic_scene"] = {
        "last_doa_angle": getattr(runtime, "_last_doa_angle", None),
        "last_doa_speech": getattr(runtime, "_last_doa_speech", None),
        "last_doa_age_sec": doa_age_sec,
        "attention_confidence": runtime._attention_confidence(now_mono),
        "attention_source": attention_source,
    }
    last_learned_preferences = getattr(runtime, "_last_learned_preferences", {})
    status["preference_learning"] = (
        dict(last_learned_preferences)
        if isinstance(last_learned_preferences, dict)
        else {}
    )
    status["multimodal_grounding"] = runtime._multimodal_grounding_snapshot()
    set_runtime_voice_state_fn(status)
    observability = getattr(runtime, "_observability", None)
    if observability is not None:
        with suppress(Exception):
            observability.record_state_transition(status.get("presence_state", "unknown"), reason="presence_state")
