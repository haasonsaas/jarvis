from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.runtime_multimodal import (
    multimodal_grounding_snapshot,
    multimodal_grounding_snapshot_for_runtime,
)


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


def test_multimodal_grounding_snapshot_for_runtime_computes_signal_ages() -> None:
    runtime = SimpleNamespace(
        presence=SimpleNamespace(
            signals=SimpleNamespace(face_last_seen=8.0, hand_last_seen=9.0, doa_last_seen=9.5),
            attention_source=lambda: "face",
        ),
        _last_doa_angle=20.0,
        _last_doa_speech=True,
        _stt_diagnostics_snapshot=lambda: {"confidence_score": 0.8, "confidence_band": "high"},
        _attention_confidence=MagicMock(return_value=0.9),
    )

    payload = multimodal_grounding_snapshot_for_runtime(
        runtime,
        recency_threshold_sec=30.0,
        now_monotonic_fn=lambda: 10.0,
    )

    assert payload["signals"]["face_recent"] is True
    assert payload["signals"]["doa_recent"] is True
    runtime._attention_confidence.assert_called_once_with(10.0)
