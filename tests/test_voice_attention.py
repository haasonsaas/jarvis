import pytest

from jarvis.voice_attention import VoiceAttentionConfig, VoiceAttentionController


pytestmark = pytest.mark.fast


def _controller(mode: str = "wake_word", calibration_profile: str = "default") -> VoiceAttentionController:
    return VoiceAttentionController(
        VoiceAttentionConfig(
            wake_words=["jarvis"],
            mode=mode,
            wake_calibration_profile=calibration_profile,
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


def test_noisy_room_profile_applies_calibration_settings():
    attention = _controller("wake_word", calibration_profile="noisy_room")
    status = attention.status(now=0.0)
    assert status["wake_calibration_profile"] == "noisy_room"
    assert status["wake_word_sensitivity"] >= 0.8
    assert status["false_trigger_threshold"] == 2
    assert status["false_trigger_window_sec"] >= 30.0


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


def test_adaptive_silence_timeout_adjusts_for_rate_and_interruptions():
    attention = _controller("always_listening")
    base_timeout = attention.silence_timeout()

    attention.register_utterance("one two", duration_sec=2.5, interruption_likelihood=0.0)
    slow_timeout = attention.silence_timeout()
    assert slow_timeout > base_timeout

    attention.register_utterance(
        "one two three four five six seven eight nine ten",
        duration_sec=1.0,
        interruption_likelihood=0.9,
    )
    fast_interrupt_timeout = attention.silence_timeout()
    assert fast_interrupt_timeout < slow_timeout


def test_status_includes_adaptive_timeout_diagnostics():
    attention = _controller("always_listening")
    attention.register_utterance("please set a timer", duration_sec=1.2, interruption_likelihood=0.25)
    status = attention.status(now=0.0)
    assert "adaptive_silence_timeout_sec" in status
    assert "speech_rate_wps" in status
    assert "interruption_likelihood" in status
    assert "wake_calibration_profile" in status
    assert "effective_wake_word_sensitivity" in status


def test_repeated_wake_word_only_triggers_suppression_window():
    attention = _controller("wake_word", calibration_profile="noisy_room")

    first = attention.process_transcript("jarvis", now=100.0)
    second = attention.process_transcript("jarvis", now=106.0)
    third = attention.process_transcript("jarvis", now=112.0)

    assert first.reason in {"wake_word_only", "wake_word_only_suppressed"}
    assert second.reason in {"wake_word_only", "wake_word_only_suppressed"}
    assert third.reason == "suppressed_false_trigger_window"
