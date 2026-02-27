from __future__ import annotations

from jarvis.runtime_preferences import (
    detect_voice_profile_updates,
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
