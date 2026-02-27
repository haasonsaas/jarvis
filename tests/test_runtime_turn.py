from __future__ import annotations

from types import SimpleNamespace

from jarvis.runtime_turn import (
    attention_confidence,
    classify_user_intent,
    compute_turn_taking,
    looks_like_user_correction,
    requires_confirmation,
    requires_stt_repair,
)


def test_classify_user_intent_and_correction_detection() -> None:
    assert classify_user_intent("Turn on the lights") == "action"
    assert classify_user_intent("Can you turn on the lights and tell me the weather?") == "hybrid"
    assert classify_user_intent("What time is it?") == "answer"
    assert looks_like_user_correction("No, I meant the office lights.") is True
    assert looks_like_user_correction("Thanks for the update.") is False


def test_attention_confidence_prioritizes_recent_signals() -> None:
    signals = SimpleNamespace(face_last_seen=98.0, hand_last_seen=99.0, doa_last_seen=99.0)
    assert attention_confidence(signals=signals, now=100.0, recency_sec=3.0) == 1.0
    signals = SimpleNamespace(face_last_seen=None, hand_last_seen=98.5, doa_last_seen=99.0)
    assert attention_confidence(signals=signals, now=100.0, recency_sec=3.0) == 0.8
    signals = SimpleNamespace(face_last_seen=None, hand_last_seen=None, doa_last_seen=99.0)
    assert attention_confidence(signals=signals, now=100.0, recency_sec=3.0) == 0.5
    assert attention_confidence(signals=None, now=100.0, recency_sec=3.0) == 0.0


def test_compute_turn_taking_handles_busy_and_non_busy_paths() -> None:
    assert compute_turn_taking(
        0.3,
        False,
        False,
        attention=0.2,
        turn_taking_threshold=0.6,
        barge_in_threshold=0.5,
    ) is False
    assert compute_turn_taking(
        0.7,
        True,
        True,
        attention=0.2,
        turn_taking_threshold=0.6,
        barge_in_threshold=0.65,
    ) is True


def test_requires_stt_repair_low_confidence_and_fallback_cases() -> None:
    assert requires_stt_repair(
        "turn on the bedroom lights",
        "action",
        looks_like_user_correction_fn=looks_like_user_correction,
        diagnostics={"confidence_band": "low", "confidence_score": 0.4, "fallback_used": False},
        repair_min_words=3,
        repair_confidence_threshold=0.55,
    ) is True
    assert requires_stt_repair(
        "set the hallway lights to warm white",
        "hybrid",
        looks_like_user_correction_fn=looks_like_user_correction,
        diagnostics={"confidence_band": "unknown", "confidence_score": 0.0, "fallback_used": True},
        repair_min_words=3,
        repair_confidence_threshold=0.55,
    ) is True
    assert requires_stt_repair(
        "actually, I meant the kitchen",
        "action",
        looks_like_user_correction_fn=looks_like_user_correction,
        diagnostics={"confidence_band": "low", "confidence_score": 0.1, "fallback_used": True},
        repair_min_words=3,
        repair_confidence_threshold=0.55,
    ) is False


def test_requires_confirmation_applies_profile_thresholds() -> None:
    assert requires_confirmation(
        attention=0.2,
        confirmations="minimal",
        last_doa_speech=False,
        intended_query_min_attention=0.35,
    ) is False
    assert requires_confirmation(
        attention=0.2,
        confirmations="strict",
        last_doa_speech=True,
        intended_query_min_attention=0.35,
    ) is True
    assert requires_confirmation(
        attention=0.2,
        confirmations="standard",
        last_doa_speech=True,
        intended_query_min_attention=0.35,
    ) is False
