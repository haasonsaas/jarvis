from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.presence import State
from jarvis.runtime_voice_status import (
    apply_turn_choreography,
    publish_voice_status,
    turn_choreography_snapshot,
)


def test_apply_turn_choreography_updates_signals_and_records_event() -> None:
    signals = SimpleNamespace(turn_lean=0.0, turn_tilt=0.0, turn_glance_yaw=0.0)
    observability = SimpleNamespace(record_event=MagicMock())
    runtime = SimpleNamespace(
        presence=SimpleNamespace(signals=signals),
        _turn_choreography={},
        _observability=observability,
    )
    cues = {
        State.THINKING: {
            "label": "think_glance_away",
            "turn_lean": 0.5,
            "turn_tilt": 2.0,
            "turn_glance_yaw": 8.0,
        }
    }

    apply_turn_choreography(runtime, State.THINKING, cues_by_state=cues, now_time_fn=lambda: 42.0)

    assert signals.turn_lean == 0.5
    assert signals.turn_tilt == 2.0
    assert signals.turn_glance_yaw == 8.0
    assert runtime._turn_choreography["label"] == "think_glance_away"
    assert runtime._turn_choreography["updated_at"] == 42.0
    observability.record_event.assert_called_once()


def test_turn_choreography_snapshot_returns_default_when_empty() -> None:
    runtime = SimpleNamespace(_turn_choreography=None)
    snapshot = turn_choreography_snapshot(runtime, idle_state_value="idle")
    assert snapshot["phase"] == "idle"
    assert snapshot["label"] == "idle_reset"
    assert snapshot["turn_lean"] == 0.0


def test_publish_voice_status_builds_payload_and_records_transition() -> None:
    voice = SimpleNamespace(status=lambda: {"mode": "wake_word"})
    signals = SimpleNamespace(state=State.LISTENING, turn_lean=0.0, turn_tilt=0.0, turn_glance_yaw=0.0)
    observability = SimpleNamespace(record_state_transition=MagicMock(), record_event=MagicMock())
    runtime = SimpleNamespace(
        _check_runtime_invariants=MagicMock(),
        _voice_controller=lambda: voice,
        presence=SimpleNamespace(signals=signals, attention_source=lambda: "face"),
        _turn_choreography={},
        _stt_diagnostics_snapshot=lambda: {"confidence_band": "unknown"},
        _active_voice_user=lambda: "operator",
        _active_voice_profile=lambda: {"verbosity": "normal"},
        _voice_user_profiles={"operator": {"verbosity": "normal"}},
        _active_control_preset="custom",
        _last_doa_update=10.0,
        _last_doa_angle=15.0,
        _last_doa_speech=True,
        _attention_confidence=lambda _now: 0.8,
        _last_learned_preferences={"user": "operator"},
        _multimodal_grounding_snapshot=lambda: {"confidence_band": "medium"},
        _observability=observability,
    )
    cues = {
        State.LISTENING: {
            "label": "listen_lean_in",
            "turn_lean": 0.6,
            "turn_tilt": 1.0,
            "turn_glance_yaw": 4.0,
        }
    }
    payload: dict[str, object] = {}

    publish_voice_status(
        runtime,
        set_runtime_voice_state_fn=lambda status: payload.update(status),
        cues_by_state=cues,
        idle_state_value="idle",
        now_monotonic_fn=lambda: 12.0,
    )

    assert payload["presence_state"] == "listening"
    assert payload["voice_profile_user"] == "operator"
    assert payload["control_preset"] == "custom"
    assert payload["turn_choreography"]["label"] == "listen_lean_in"
    assert payload["acoustic_scene"]["attention_confidence"] == 0.8
    observability.record_state_transition.assert_called_once_with("listening", reason="presence_state")


def test_publish_voice_status_handles_presence_state_failures() -> None:
    voice = SimpleNamespace(status=lambda: {})
    runtime = SimpleNamespace(
        _check_runtime_invariants=MagicMock(),
        _voice_controller=lambda: voice,
        presence=SimpleNamespace(signals=SimpleNamespace(), attention_source=lambda: "unknown"),
        _turn_choreography={},
        _stt_diagnostics_snapshot=lambda: {"confidence_band": "unknown"},
        _active_voice_user=lambda: "operator",
        _active_voice_profile=lambda: {"verbosity": "normal"},
        _voice_user_profiles={},
        _active_control_preset="custom",
        _last_doa_update=0.0,
        _last_doa_angle=None,
        _last_doa_speech=None,
        _attention_confidence=lambda _now: 0.0,
        _last_learned_preferences={},
        _multimodal_grounding_snapshot=lambda: {},
        _observability=None,
    )
    payload: dict[str, object] = {}

    publish_voice_status(
        runtime,
        set_runtime_voice_state_fn=lambda status: payload.update(status),
        cues_by_state={},
        idle_state_value="idle",
        now_monotonic_fn=lambda: 1.0,
    )

    assert payload["presence_state"] == "unknown"
