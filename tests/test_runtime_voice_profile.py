from __future__ import annotations

from types import SimpleNamespace

from jarvis.runtime_constants import (
    VALID_VOICE_PROFILE_CONFIRMATIONS,
    VALID_VOICE_PROFILE_PACE,
    VALID_VOICE_PROFILE_TONE,
    VALID_VOICE_PROFILE_VERBOSITY,
)
from jarvis.runtime_voice_profile import (
    active_voice_profile,
    active_voice_user,
    parse_control_bool,
    parse_control_choice,
    with_voice_profile_guidance,
)


def _runtime_stub(*, default_user: str = "operator", profiles: object = None) -> SimpleNamespace:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(identity_default_user=default_user)
    runtime._voice_user_profiles = profiles if profiles is not None else {}
    runtime._parse_control_choice = parse_control_choice
    return runtime


def test_parse_control_bool_accepts_bool_int_and_string_values() -> None:
    assert parse_control_bool(True) is True
    assert parse_control_bool(1) is True
    assert parse_control_bool("yes") is True
    assert parse_control_bool(False) is False
    assert parse_control_bool(0) is False
    assert parse_control_bool("off") is False
    assert parse_control_bool("maybe") is None


def test_parse_control_choice_filters_to_allowed_set() -> None:
    allowed = {"a", "b"}
    assert parse_control_choice("A", allowed) == "a"
    assert parse_control_choice("b", allowed) == "b"
    assert parse_control_choice("c", allowed) is None
    assert parse_control_choice(1, allowed) is None


def test_active_voice_user_defaults_to_operator() -> None:
    runtime = _runtime_stub(default_user="")
    assert active_voice_user(runtime) == "operator"


def test_active_voice_profile_applies_valid_user_overrides() -> None:
    runtime = _runtime_stub(
        profiles={
            "operator": {
                "verbosity": "brief",
                "confirmations": "minimal",
                "pace": "fast",
                "tone": "direct",
                "ignored": "value",
            }
        }
    )

    profile = active_voice_profile(
        runtime,
        user="operator",
        valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
        valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
        valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
        valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
    )

    assert profile == {
        "verbosity": "brief",
        "confirmations": "minimal",
        "pace": "fast",
        "tone": "direct",
    }


def test_with_voice_profile_guidance_only_appends_for_non_default_preferences() -> None:
    runtime = _runtime_stub(
        profiles={"operator": {"verbosity": "brief", "tone": "formal"}}
    )

    guided = with_voice_profile_guidance(
        runtime,
        "Turn on the lights.",
        valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
        valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
        valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
        valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
    )
    assert "Voice profile preference" in guided
    assert "concise" in guided
    assert "formal, composed phrasing" in guided

    neutral_runtime = _runtime_stub(profiles={"operator": {"verbosity": "normal", "tone": "auto"}})
    neutral = with_voice_profile_guidance(
        neutral_runtime,
        "Turn on the lights.",
        valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
        valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
        valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
        valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
    )
    assert neutral == "Turn on the lights."
