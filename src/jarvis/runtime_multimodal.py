"""Multimodal grounding helpers for runtime status and turn confidence."""

from __future__ import annotations

import math
import time
from contextlib import suppress

from typing import Any, Callable


def _safe_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _confidence_band(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def multimodal_grounding_snapshot(
    *,
    face_age_sec: float | None,
    hand_age_sec: float | None,
    doa_age_sec: float | None,
    doa_angle: float | None,
    doa_speech: bool | None,
    stt_diagnostics: dict[str, Any] | None,
    attention_confidence: float,
    attention_source: str,
    recency_threshold_sec: float,
) -> dict[str, Any]:
    threshold = _safe_float(
        recency_threshold_sec,
        30.0,
        minimum=1.0,
        maximum=300.0,
    )
    face_recent = (
        face_age_sec is not None
        and _safe_float(face_age_sec, threshold + 1.0, minimum=0.0) <= threshold
    )
    hand_recent = (
        hand_age_sec is not None
        and _safe_float(hand_age_sec, threshold + 1.0, minimum=0.0) <= threshold
    )
    doa_recent = (
        doa_age_sec is not None
        and _safe_float(doa_age_sec, threshold + 1.0, minimum=0.0) <= threshold
        and doa_angle is not None
    )

    stt = stt_diagnostics if isinstance(stt_diagnostics, dict) else {}
    stt_confidence = _safe_float(
        stt.get("confidence_score"),
        0.0,
        minimum=0.0,
        maximum=1.0,
    )
    stt_band = str(stt.get("confidence_band", "unknown")).strip().lower()
    if stt_band not in {"unknown", "low", "medium", "high"}:
        stt_band = _confidence_band(stt_confidence)

    normalized_attention_confidence = _safe_float(
        attention_confidence,
        0.0,
        minimum=0.0,
        maximum=1.0,
    )
    source = str(attention_source or "unknown").strip().lower() or "unknown"

    presence_signal = max(
        normalized_attention_confidence,
        1.0 if face_recent else 0.0,
        0.8 if hand_recent else 0.0,
        0.5 if doa_recent else 0.0,
    )
    doa_signal = 0.0
    if doa_recent:
        doa_signal = 0.75 if doa_speech is False else 1.0
    source_signal = (
        1.0
        if source == "face"
        else 0.85
        if source in {"hand", "doa"}
        else 0.6
    )

    overall = (
        (0.55 * presence_signal)
        + (0.35 * stt_confidence)
        + (0.10 * source_signal)
    )
    if stt_band == "low" and not face_recent:
        overall *= 0.8
    if not face_recent and not hand_recent and not doa_recent:
        overall *= 0.8
    overall = _safe_float(overall, 0.0, minimum=0.0, maximum=1.0)

    reasons: list[str] = []
    if not face_recent:
        reasons.append("face_signal_stale")
    if not hand_recent:
        reasons.append("hand_signal_stale")
    if not doa_recent:
        reasons.append("doa_signal_stale")
    if doa_recent and doa_speech is False:
        reasons.append("doa_reports_non_speech")
    if stt_band == "low":
        reasons.append("stt_low_confidence")
    if source == "unknown":
        reasons.append("attention_source_unknown")
    if not reasons:
        reasons.append("grounded")

    return {
        "overall_confidence": overall,
        "confidence_band": _confidence_band(overall),
        "attention_source": source,
        "modality_scores": {
            "presence": presence_signal,
            "stt": stt_confidence,
            "source": source_signal,
            "doa": doa_signal,
        },
        "signals": {
            "face_recent": face_recent,
            "hand_recent": hand_recent,
            "doa_recent": doa_recent,
            "doa_speech": doa_speech,
            "stt_band": stt_band,
        },
        "reasons": reasons,
    }


def multimodal_grounding_snapshot_for_runtime(
    runtime: Any,
    *,
    recency_threshold_sec: float,
    now_monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    signals = getattr(runtime.presence, "signals", None)
    now_mono = now_monotonic_fn()
    face_age_sec: float | None = None
    hand_age_sec: float | None = None
    doa_age_sec: float | None = None
    if signals is not None:
        face_last_seen = getattr(signals, "face_last_seen", None)
        hand_last_seen = getattr(signals, "hand_last_seen", None)
        doa_last_seen = getattr(signals, "doa_last_seen", None)
        if face_last_seen:
            face_age_sec = max(0.0, now_mono - float(face_last_seen))
        if hand_last_seen:
            hand_age_sec = max(0.0, now_mono - float(hand_last_seen))
        if doa_last_seen:
            doa_age_sec = max(0.0, now_mono - float(doa_last_seen))
    attention_source = "unknown"
    with suppress(Exception):
        attention_source = str(runtime.presence.attention_source())
    return multimodal_grounding_snapshot(
        face_age_sec=face_age_sec,
        hand_age_sec=hand_age_sec,
        doa_age_sec=doa_age_sec,
        doa_angle=getattr(runtime, "_last_doa_angle", None),
        doa_speech=getattr(runtime, "_last_doa_speech", None),
        stt_diagnostics=runtime._stt_diagnostics_snapshot(),
        attention_confidence=runtime._attention_confidence(now_mono),
        attention_source=attention_source,
        recency_threshold_sec=recency_threshold_sec,
    )
