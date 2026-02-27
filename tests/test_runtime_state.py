from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.runtime_constants import (
    EPISODIC_TIMELINE_MAXLEN,
    RUNTIME_INVARIANT_HISTORY_MAXLEN,
    VALID_BACKCHANNEL_STYLES,
    VALID_CONTROL_PRESETS,
    VALID_PERSONA_STYLES,
    VALID_VOICE_PROFILE_CONFIRMATIONS,
    VALID_VOICE_PROFILE_PACE,
    VALID_VOICE_PROFILE_TONE,
    VALID_VOICE_PROFILE_VERBOSITY,
)
from jarvis.runtime_state import (
    apply_runtime_profile,
    check_runtime_invariants,
    load_runtime_state,
    runtime_profile_snapshot,
    save_runtime_state,
)
from jarvis.voice_attention import (
    VALID_TIMEOUT_PROFILES,
    VALID_WAKE_MODES,
    VoiceAttentionConfig,
    VoiceAttentionController,
)


def _parse_control_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in {0, 1}:
            return bool(value)
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return None


def _parse_control_choice(value: object, allowed: set[str]) -> str | None:
    choice = str(value or "").strip().lower()
    if not choice:
        return None
    if choice in allowed:
        return choice
    return None


def _build_runtime(*, state_path: Path | None = None) -> SimpleNamespace:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(
        motion_enabled=True,
        home_enabled=True,
        safe_mode_enabled=False,
        persona_style="composed",
        backchannel_style="balanced",
    )
    runtime.presence = SimpleNamespace(
        start=MagicMock(),
        stop=MagicMock(),
        set_backchannel_style=MagicMock(),
    )
    runtime._voice_attention = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
    runtime._voice_user_profiles = {}
    runtime._active_control_preset = "custom"
    runtime._tts_output_enabled = True
    runtime._awaiting_confirmation = False
    runtime._pending_text = None
    runtime._awaiting_repair_confirmation = False
    runtime._repair_candidate_text = None
    runtime._episode_seq = 0
    runtime._episodic_timeline = deque(maxlen=EPISODIC_TIMELINE_MAXLEN)
    runtime._runtime_state_path = state_path
    runtime._personality_preview_snapshot = None
    runtime._runtime_invariant_checked_at = 0.0
    runtime._runtime_invariant_checked_monotonic = 0.0
    runtime._runtime_invariant_violations_total = 0
    runtime._runtime_invariant_auto_heals_total = 0
    runtime._runtime_invariant_recent = deque(maxlen=RUNTIME_INVARIANT_HISTORY_MAXLEN)
    runtime._observability = None
    runtime._publish_voice_status = MagicMock()
    runtime._persist_runtime_state_safe = MagicMock()

    runtime._parse_control_bool = _parse_control_bool
    runtime._parse_control_choice = _parse_control_choice

    def _set_persona_style(style: str) -> None:
        runtime.config.persona_style = style

    runtime._set_persona_style = _set_persona_style
    runtime._voice_controller = lambda: runtime._voice_attention
    return runtime


def _save(runtime: SimpleNamespace) -> None:
    save_runtime_state(
        runtime,
        episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
        valid_persona_styles=VALID_PERSONA_STYLES,
        valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
    )


def _load(runtime: SimpleNamespace, *, set_safe_mode_fn: MagicMock) -> None:
    load_runtime_state(
        runtime,
        episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
        valid_persona_styles=VALID_PERSONA_STYLES,
        valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
        valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
        valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
        valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
        valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
        valid_control_presets=VALID_CONTROL_PRESETS,
        set_safe_mode_fn=set_safe_mode_fn,
    )


def test_runtime_state_round_trip_restore(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime-state.json"
    source = _build_runtime(state_path=state_path)
    source._voice_attention.set_mode("push_to_talk")
    source._voice_attention.set_timeout_profile("long")
    source._voice_attention.set_push_to_talk_active(True)
    source._voice_attention.sleeping = True
    source.config.motion_enabled = False
    source.config.home_enabled = False
    source.config.safe_mode_enabled = True
    source.config.persona_style = "friendly"
    source.config.backchannel_style = "expressive"
    source._tts_output_enabled = False
    source._voice_user_profiles = {
        "operator": {
            "verbosity": "brief",
            "confirmations": "minimal",
            "pace": "fast",
            "tone": "formal",
        }
    }
    source._active_control_preset = "quiet_hours"
    source._awaiting_confirmation = True
    source._pending_text = "lock doors"
    source._awaiting_repair_confirmation = True
    source._repair_candidate_text = "turn off office lamp"
    source._episode_seq = 7
    source._episodic_timeline = deque(
        [
            {
                "episode_id": 7,
                "timestamp": 1700000000.0,
                "turn_id": 12,
                "intent": "action",
                "lifecycle": "completed",
                "summary": "Lock doors and turn off office lamp",
                "tool_count": 2,
                "completion_success": True,
                "response_success": True,
            }
        ],
        maxlen=EPISODIC_TIMELINE_MAXLEN,
    )

    _save(source)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["runtime"]["active_control_preset"] == "quiet_hours"
    assert payload["runtime"]["voice_user_profiles"]["operator"]["verbosity"] == "brief"

    restored = _build_runtime(state_path=state_path)
    restored.config.motion_enabled = True
    restored.config.home_enabled = True
    restored.config.safe_mode_enabled = False
    restored.config.persona_style = "composed"
    restored.config.backchannel_style = "balanced"

    set_safe_mode = MagicMock()
    _load(restored, set_safe_mode_fn=set_safe_mode)

    assert restored._voice_attention.mode == "push_to_talk"
    assert restored._voice_attention.timeout_profile == "long"
    assert restored._voice_attention.push_to_talk_active is True
    assert restored._voice_attention.sleeping is True
    assert restored.config.motion_enabled is False
    assert restored.config.home_enabled is False
    assert restored.config.safe_mode_enabled is True
    assert restored._tts_output_enabled is False
    assert restored.config.persona_style == "friendly"
    assert restored.config.backchannel_style == "expressive"
    assert restored._active_control_preset == "quiet_hours"
    assert restored._pending_text == "lock doors"
    assert restored._repair_candidate_text == "turn off office lamp"
    assert restored._episode_seq == 7
    assert len(restored._episodic_timeline) == 1
    set_safe_mode.assert_called_once_with(True)


def test_check_runtime_invariants_auto_heals_mismatch() -> None:
    runtime = _build_runtime()
    runtime._voice_attention.set_mode("push_to_talk")
    runtime._voice_attention.set_push_to_talk_active(False)
    runtime._active_control_preset = "invalid-preset"

    snapshot = check_runtime_invariants(
        runtime,
        auto_heal=True,
        runtime_invariant_history_maxlen=RUNTIME_INVARIANT_HISTORY_MAXLEN,
        valid_control_presets=VALID_CONTROL_PRESETS,
    )

    assert runtime._voice_attention.push_to_talk_active is True
    assert runtime._active_control_preset == "custom"
    assert snapshot["total_violations"] == 2
    assert snapshot["total_auto_heals"] == 2
    runtime._persist_runtime_state_safe.assert_called_once()


def test_apply_runtime_profile_updates_runtime_and_persists() -> None:
    runtime = _build_runtime()
    profile = {
        "wake_mode": "always_listening",
        "sleeping": False,
        "timeout_profile": "short",
        "push_to_talk_active": False,
        "motion_enabled": False,
        "home_enabled": False,
        "safe_mode_enabled": True,
        "tts_enabled": False,
        "persona_style": "friendly",
        "backchannel_style": "quiet",
        "voice_user_profiles": {
            "Operator": {
                "verbosity": "brief",
                "confirmations": "minimal",
                "pace": "fast",
                "tone": "direct",
            },
            "": {"verbosity": "detailed"},
        },
    }
    set_safe_mode = MagicMock()

    snapshot = apply_runtime_profile(
        runtime,
        profile,
        mark_custom=True,
        valid_wake_modes=VALID_WAKE_MODES,
        valid_timeout_profiles=VALID_TIMEOUT_PROFILES,
        valid_persona_styles=VALID_PERSONA_STYLES,
        valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
        valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
        valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
        valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
        valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
        set_safe_mode_fn=set_safe_mode,
    )

    assert runtime._voice_attention.mode == "always_listening"
    assert runtime._voice_attention.timeout_profile == "short"
    assert runtime.config.motion_enabled is False
    assert runtime.config.home_enabled is False
    assert runtime.config.safe_mode_enabled is True
    assert runtime._tts_output_enabled is False
    assert runtime.config.persona_style == "friendly"
    assert runtime.config.backchannel_style == "quiet"
    assert runtime._voice_user_profiles["operator"]["verbosity"] == "brief"
    assert runtime._active_control_preset == "custom"
    runtime.presence.stop.assert_called_once()
    runtime.presence.set_backchannel_style.assert_called_once_with("quiet")
    set_safe_mode.assert_called_once_with(True)
    runtime._publish_voice_status.assert_called_once()
    runtime._persist_runtime_state_safe.assert_called_once()
    assert snapshot["active_control_preset"] == "custom"


def test_runtime_profile_snapshot_sanitizes_voice_profiles() -> None:
    runtime = _build_runtime()
    runtime._voice_user_profiles = {
        "operator": {"verbosity": "brief"},
        "bad": "not-a-dict",
    }

    snapshot = runtime_profile_snapshot(runtime)

    assert snapshot["voice_user_profiles"] == {"operator": {"verbosity": "brief"}}
