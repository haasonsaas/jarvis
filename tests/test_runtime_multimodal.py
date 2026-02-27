from __future__ import annotations

from jarvis.runtime_multimodal import multimodal_grounding_snapshot


def test_multimodal_grounding_snapshot_high_confidence() -> None:
    payload = multimodal_grounding_snapshot(
        face_age_sec=1.0,
        hand_age_sec=2.0,
        doa_age_sec=1.0,
        doa_angle=20.0,
        doa_speech=True,
        stt_diagnostics={"confidence_score": 0.92, "confidence_band": "high"},
        attention_confidence=1.0,
        attention_source="face",
        recency_threshold_sec=30.0,
    )
    assert payload["confidence_band"] in {"high", "medium"}
    assert payload["overall_confidence"] >= 0.75
    assert payload["signals"]["face_recent"] is True


def test_multimodal_grounding_snapshot_low_confidence_reasons() -> None:
    payload = multimodal_grounding_snapshot(
        face_age_sec=120.0,
        hand_age_sec=120.0,
        doa_age_sec=120.0,
        doa_angle=None,
        doa_speech=None,
        stt_diagnostics={"confidence_score": 0.15, "confidence_band": "low"},
        attention_confidence=0.1,
        attention_source="unknown",
        recency_threshold_sec=30.0,
    )
    assert payload["confidence_band"] == "low"
    reasons = set(payload["reasons"])
    assert "face_signal_stale" in reasons
    assert "stt_low_confidence" in reasons
    assert "attention_source_unknown" in reasons


def test_multimodal_grounding_snapshot_context_downgrades_non_speech_doa() -> None:
    payload = multimodal_grounding_snapshot(
        face_age_sec=None,
        hand_age_sec=None,
        doa_age_sec=5.0,
        doa_angle=15.0,
        doa_speech=False,
        stt_diagnostics={"confidence_score": 0.7, "confidence_band": "medium"},
        attention_confidence=0.5,
        attention_source="doa",
        recency_threshold_sec=30.0,
    )
    assert payload["signals"]["doa_recent"] is True
    assert payload["signals"]["doa_speech"] is False
    assert "doa_reports_non_speech" in payload["reasons"]
