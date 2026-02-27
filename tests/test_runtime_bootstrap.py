from __future__ import annotations

from types import SimpleNamespace

from jarvis.runtime_bootstrap import (
    apply_cli_overrides,
    build_observability_store,
    build_skill_registry,
    build_voice_attention_controller,
    initialize_runtime_fields,
    telemetry_defaults,
)


def test_apply_cli_overrides_respects_disable_flags() -> None:
    config = SimpleNamespace(motion_enabled=True, home_enabled=True, hand_track_enabled=True)
    args = SimpleNamespace(no_motion=True, no_home=True, no_hands=False)

    apply_cli_overrides(config, args)

    assert config.motion_enabled is False
    assert config.home_enabled is False
    assert config.hand_track_enabled is True


def test_build_voice_attention_controller_uses_config_values() -> None:
    config = SimpleNamespace(
        wake_words=["jarvis", "hey jarvis"],
        wake_mode="wake_word",
        wake_calibration_profile="balanced",
        wake_word_sensitivity=0.42,
        voice_followup_window_sec=4.0,
        voice_timeout_profile="normal",
        voice_timeout_short_sec=3.0,
        voice_timeout_normal_sec=8.0,
        voice_timeout_long_sec=20.0,
        barge_threshold_always_listening=0.55,
        barge_threshold_wake_word=0.65,
        barge_threshold_push_to_talk=0.75,
        voice_min_post_wake_chars=2,
        voice_room_default="office",
    )

    controller = build_voice_attention_controller(config)
    snapshot = controller.status(now=0.0)

    assert controller.mode == "wake_word"
    assert snapshot["wake_words"] == ["jarvis", "hey jarvis"]
    assert controller.active_room == "office"


def test_build_skill_registry_discovers_empty_directory(tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    config = SimpleNamespace(
        skills_dir=str(skills_dir),
        skills_allowlist=[],
        skills_require_signature=False,
        skills_signature_key="",
        skills_enabled=True,
        skills_state_path=str(tmp_path / "skills-state.json"),
    )

    registry = build_skill_registry(config)

    assert registry.enabled is True
    assert registry.status_snapshot()["loaded_count"] == 0


def test_build_observability_store_disabled_returns_none(tmp_path) -> None:
    config = SimpleNamespace(
        observability_enabled=False,
        observability_db_path=str(tmp_path / "observability.db"),
        observability_state_path=str(tmp_path / "observability-state.json"),
        observability_event_log_path=str(tmp_path / "observability-events.jsonl"),
        observability_failure_burst_threshold=3,
    )

    assert build_observability_store(config) is None


def test_initialize_runtime_fields_sets_defaults() -> None:
    runtime = SimpleNamespace(_default_stt_diagnostics=lambda: {"confidence_band": "unknown"})

    initialize_runtime_fields(
        runtime,
        state_idle_value="idle",
        conversation_trace_maxlen=3,
        episodic_timeline_maxlen=4,
        runtime_invariant_history_maxlen=5,
    )

    assert runtime._turn_choreography["phase"] == "idle"
    assert runtime._tts_gain == 1.0
    assert runtime._active_control_preset == "custom"
    assert runtime._telemetry == telemetry_defaults()
    assert runtime._conversation_traces.maxlen == 3
    assert runtime._episodic_timeline.maxlen == 4
    assert runtime._runtime_invariant_recent.maxlen == 5
