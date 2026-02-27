from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.runtime_preferences import (
    detect_voice_profile_updates,
    learn_voice_preferences,
    voice_profile_summary,
)


def test_detect_voice_profile_updates_extracts_multiple_fields() -> None:
    updates = detect_voice_profile_updates(
        "Please be brief, speak slower, and use a formal tone."
    )
    assert updates["verbosity"] == "brief"
    assert updates["pace"] == "slow"
    assert updates["tone"] == "formal"


def test_detect_voice_profile_updates_requires_style_hints() -> None:
    updates = detect_voice_profile_updates("Could you check the weather in Boston?")
    assert updates == {}


def test_detect_voice_profile_updates_handles_confirmation_preferences() -> None:
    updates = detect_voice_profile_updates(
        "I prefer fewer confirmations, and please be more direct."
    )
    assert updates["confirmations"] == "minimal"
    assert updates["tone"] == "direct"


def test_voice_profile_summary_renders_expected_shape() -> None:
    text = voice_profile_summary(
        {
            "verbosity": "detailed",
            "confirmations": "strict",
            "pace": "fast",
            "tone": "empathetic",
        }
    )
    assert "verbosity=detailed" in text
    assert "confirmations=strict" in text
    assert "pace=fast" in text
    assert "tone=empathetic" in text


def test_learn_voice_preferences_updates_profile_memory_and_telemetry() -> None:
    memory = SimpleNamespace(upsert_summary=MagicMock())
    runtime = SimpleNamespace(
        _parse_control_choice=lambda value, valid: value if value in valid else None,
        _active_voice_user=lambda: "operator",
        _active_voice_profile=lambda user=None: {},
        _voice_user_profiles={},
        _telemetry={"preference_update_turns": 0.0, "preference_update_fields": 0.0},
        _last_learned_preferences={},
        brain=SimpleNamespace(_memory=memory),
        _persist_runtime_state_safe=MagicMock(),
        _publish_voice_status=MagicMock(),
    )

    updates = learn_voice_preferences(
        runtime,
        "Please be brief and speak slower.",
        now_ts=12.0,
        valid_voice_profile_verbosity={"normal", "brief", "detailed"},
        valid_voice_profile_confirmations={"standard", "minimal", "strict"},
        valid_voice_profile_pace={"normal", "slow", "fast"},
        valid_voice_profile_tone={"auto", "formal", "direct", "empathetic", "witty"},
    )

    assert updates == {"verbosity": "brief", "pace": "slow"}
    assert runtime._voice_user_profiles["operator"]["verbosity"] == "brief"
    assert runtime._telemetry["preference_update_turns"] == 1.0
    assert runtime._telemetry["preference_update_fields"] == 2.0
    assert runtime._last_learned_preferences["applied_at"] == 12.0
    memory.upsert_summary.assert_called_once()
    runtime._persist_runtime_state_safe.assert_called_once()
    runtime._publish_voice_status.assert_called_once()


def test_learn_voice_preferences_returns_empty_without_style_updates() -> None:
    runtime = SimpleNamespace(
        _parse_control_choice=lambda value, valid: value if value in valid else None,
        _active_voice_user=lambda: "operator",
        _active_voice_profile=lambda user=None: {},
        _voice_user_profiles={},
        _telemetry={},
        _last_learned_preferences={},
        brain=SimpleNamespace(_memory=None),
        _persist_runtime_state_safe=MagicMock(),
        _publish_voice_status=MagicMock(),
    )

    updates = learn_voice_preferences(
        runtime,
        "Could you check the weather?",
        valid_voice_profile_verbosity={"normal", "brief", "detailed"},
        valid_voice_profile_confirmations={"standard", "minimal", "strict"},
        valid_voice_profile_pace={"normal", "slow", "fast"},
        valid_voice_profile_tone={"auto", "formal", "direct", "empathetic", "witty"},
    )

    assert updates == {}
    runtime._persist_runtime_state_safe.assert_not_called()
    runtime._publish_voice_status.assert_not_called()
