import pytest

from jarvis.voice_attention import VoiceAttentionConfig, VoiceAttentionController


pytestmark = pytest.mark.fast


def _controller(mode: str = "wake_word") -> VoiceAttentionController:
    return VoiceAttentionController(
        VoiceAttentionConfig(
            wake_words=["jarvis"],
            mode=mode,
            wake_word_sensitivity=0.8,
            followup_window_sec=5.0,
        )
    )


def test_wake_word_mode_requires_wake_word_outside_followup_window():
    attention = _controller("wake_word")
    denied = attention.process_transcript("turn on the lights", now=100.0)
    assert denied.accepted is False
    assert denied.reason == "missing_wake_word"

    allowed = attention.process_transcript("jarvis turn on the lights", now=101.0)
    assert allowed.accepted is True
    assert allowed.reason == "accepted_wake_word"
    assert "turn on the lights" in allowed.text


def test_followup_window_allows_multi_turn_without_repeating_wake_word():
    attention = _controller("wake_word")
    first = attention.process_transcript("jarvis what time is it", now=200.0)
    assert first.accepted is True

    followup = attention.process_transcript("and what about tomorrow", now=202.0)
    assert followup.accepted is True
    assert followup.reason == "accepted_followup"


def test_push_to_talk_mode_blocks_until_activated():
    attention = _controller("push_to_talk")
    denied = attention.process_transcript("hello there", now=300.0)
    assert denied.accepted is False
    assert denied.reason == "push_to_talk_inactive"

    attention.set_push_to_talk_active(True)
    allowed = attention.process_transcript("hello there", now=301.0)
    assert allowed.accepted is True
    assert allowed.reason == "accepted_push_to_talk"


def test_confirmation_grammar_supports_confirm_deny_repeat():
    attention = _controller("always_listening")
    assert attention.confirmation_intent("confirm") == "confirm"
    assert attention.confirmation_intent("no") == "deny"
    assert attention.confirmation_intent("repeat") == "repeat"
    assert attention.confirmation_intent("maybe") is None


def test_sleep_and_wake_commands_toggle_state():
    attention = _controller("wake_word")

    sleep = attention.process_transcript("jarvis sleep", now=400.0)
    assert sleep.accepted is False
    assert attention.sleeping is True

    sleeping_denied = attention.process_transcript("what time is it", now=401.0)
    assert sleeping_denied.accepted is False
    assert sleeping_denied.reason == "sleeping"

    wake = attention.process_transcript("jarvis wake", now=402.0)
    assert wake.accepted is False
    assert attention.sleeping is False

    after_wake = attention.process_transcript("jarvis status", now=403.0)
    assert after_wake.accepted is True


def test_room_routing_updates_from_doa():
    attention = _controller("always_listening")
    attention.update_room_from_doa(-80.0)
    assert attention.status(now=0.0)["active_room"] == "left"
    attention.update_room_from_doa(0.0)
    assert attention.status(now=0.0)["active_room"] == "center"
    attention.update_room_from_doa(80.0)
    assert attention.status(now=0.0)["active_room"] == "right"
