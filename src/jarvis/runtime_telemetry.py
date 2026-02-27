"""Telemetry, analytics, and STT/TTS runtime helpers for Jarvis main loop."""

from __future__ import annotations

import math
import re
import time
from contextlib import suppress
from typing import Any

import numpy as np


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0.0:
        return float(values[0])
    if q >= 1.0:
        return float(values[-1])
    idx = (len(values) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return float(values[lo] + ((values[hi] - values[lo]) * frac))


def conversation_latency_analytics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    if not traces:
        return {
            "sample_count": 0,
            "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "by_intent": {},
            "by_tool_mix": {},
            "by_wake_mode": {},
        }

    def extract_total(item: dict[str, Any]) -> float:
        if not isinstance(item, dict):
            return 0.0
        latencies = item.get("latencies_ms")
        if not isinstance(latencies, dict):
            return 0.0
        try:
            value = float(latencies.get("total", 0.0))
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(value) or value < 0.0:
            return 0.0
        return value

    def pack(values: list[float]) -> dict[str, float]:
        ordered = sorted(v for v in values if math.isfinite(v) and v >= 0.0)
        return {
            "p50": percentile(ordered, 0.5),
            "p95": percentile(ordered, 0.95),
            "p99": percentile(ordered, 0.99),
        }

    overall_values = [extract_total(item) for item in traces]
    by_intent: dict[str, list[float]] = {}
    by_tool_mix: dict[str, list[float]] = {}
    by_wake_mode: dict[str, list[float]] = {}
    for item in traces:
        if not isinstance(item, dict):
            continue
        total = extract_total(item)
        intent = str(item.get("intent", "unknown")).strip().lower() or "unknown"
        by_intent.setdefault(intent, []).append(total)
        tools = item.get("tool_calls")
        tool_count = len(tools) if isinstance(tools, list) else 0
        if tool_count <= 0:
            tool_mix = "none"
        elif tool_count == 1:
            tool_mix = "single"
        else:
            tool_mix = "multi"
        by_tool_mix.setdefault(tool_mix, []).append(total)
        wake_mode = str(item.get("wake_mode", "unknown")).strip().lower() or "unknown"
        by_wake_mode.setdefault(wake_mode, []).append(total)

    return {
        "sample_count": len(overall_values),
        "overall_total_ms": pack(overall_values),
        "by_intent": {name: pack(values) for name, values in sorted(by_intent.items())},
        "by_tool_mix": {name: pack(values) for name, values in sorted(by_tool_mix.items())},
        "by_wake_mode": {name: pack(values) for name, values in sorted(by_wake_mode.items())},
    }


def policy_decision_analytics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    totals_by_tool: dict[str, int] = {}
    totals_by_reason: dict[str, int] = {}
    totals_by_status: dict[str, int] = {}
    totals_by_user: dict[str, int] = {}
    by_user_tool: dict[str, dict[str, int]] = {}
    total_decisions = 0
    for item in traces:
        if not isinstance(item, dict):
            continue
        requester = str(item.get("requester_user", "unknown")).strip().lower() or "unknown"
        decisions = item.get("policy_decisions")
        if not isinstance(decisions, list):
            continue
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            total_decisions += 1
            tool = str(decision.get("tool", "unknown")).strip().lower() or "unknown"
            status = str(decision.get("status", "unknown")).strip().lower() or "unknown"
            reason = str(decision.get("detail", "unknown")).strip().lower() or "unknown"
            totals_by_tool[tool] = totals_by_tool.get(tool, 0) + 1
            totals_by_status[status] = totals_by_status.get(status, 0) + 1
            totals_by_reason[reason] = totals_by_reason.get(reason, 0) + 1
            totals_by_user[requester] = totals_by_user.get(requester, 0) + 1
            if requester not in by_user_tool:
                by_user_tool[requester] = {}
            user_tool = by_user_tool[requester]
            user_tool[tool] = user_tool.get(tool, 0) + 1

    return {
        "decision_count": total_decisions,
        "by_tool": {name: totals_by_tool[name] for name in sorted(totals_by_tool)},
        "by_status": {name: totals_by_status[name] for name in sorted(totals_by_status)},
        "by_reason": {name: totals_by_reason[name] for name in sorted(totals_by_reason)},
        "by_user": {name: totals_by_user[name] for name in sorted(totals_by_user)},
        "by_user_tool": {
            user: {tool: by_user_tool[user][tool] for tool in sorted(by_user_tool[user])}
            for user in sorted(by_user_tool)
        },
    }


def default_stt_diagnostics() -> dict[str, Any]:
    return {
        "source": "none",
        "fallback_used": False,
        "confidence_score": 0.0,
        "confidence_band": "unknown",
        "avg_logprob": -3.0,
        "avg_no_speech_prob": 1.0,
        "language": "unknown",
        "language_probability": 0.0,
        "segment_count": 0,
        "word_count": 0,
        "char_count": 0,
        "updated_at": 0.0,
        "error": "",
    }


def stt_confidence_band(score: float, *, has_words: bool) -> str:
    if not has_words:
        return "unknown"
    if score >= 0.78:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def stt_diagnostics_snapshot(current: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = default_stt_diagnostics()
    if isinstance(current, dict):
        for key in snapshot:
            if key in current:
                snapshot[key] = current[key]

    def safe_float(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
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

    def safe_int(value: Any, default: int = 0) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, number)

    snapshot["source"] = str(snapshot.get("source", "none")).strip().lower() or "none"
    snapshot["fallback_used"] = bool(snapshot.get("fallback_used", False))
    snapshot["confidence_score"] = safe_float(snapshot.get("confidence_score"), 0.0, minimum=0.0, maximum=1.0)
    band = str(snapshot.get("confidence_band", "unknown")).strip().lower()
    if band not in {"unknown", "low", "medium", "high"}:
        band = stt_confidence_band(
            float(snapshot["confidence_score"]),
            has_words=safe_int(snapshot.get("word_count")) > 0,
        )
    snapshot["confidence_band"] = band
    snapshot["avg_logprob"] = safe_float(snapshot.get("avg_logprob"), -3.0)
    snapshot["avg_no_speech_prob"] = safe_float(
        snapshot.get("avg_no_speech_prob"),
        1.0,
        minimum=0.0,
        maximum=1.0,
    )
    snapshot["language"] = str(snapshot.get("language", "unknown")).strip().lower() or "unknown"
    snapshot["language_probability"] = safe_float(
        snapshot.get("language_probability"),
        0.0,
        minimum=0.0,
        maximum=1.0,
    )
    snapshot["segment_count"] = safe_int(snapshot.get("segment_count"))
    snapshot["word_count"] = safe_int(snapshot.get("word_count"))
    snapshot["char_count"] = safe_int(snapshot.get("char_count"))
    snapshot["updated_at"] = safe_float(snapshot.get("updated_at"), 0.0, minimum=0.0)
    snapshot["error"] = str(snapshot.get("error", "")).strip().lower()
    return snapshot


def transcribe_with_optional_diagnostics(model: Any, audio: np.ndarray) -> tuple[str, dict[str, Any]]:
    diagnostics_method = getattr(model, "transcribe_with_diagnostics", None)
    if callable(diagnostics_method):
        with suppress(Exception):
            result = diagnostics_method(audio)
            if isinstance(result, tuple) and len(result) == 2:
                text = str(result[0] or "")
                diagnostics = result[1]
                if isinstance(diagnostics, dict):
                    return text, {str(key): value for key, value in diagnostics.items()}
                return text, {}
    text = model.transcribe(audio)
    return str(text or ""), {}


def update_stt_diagnostics(
    *,
    text: str,
    source: str,
    fallback_used: bool,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = default_stt_diagnostics()
    diag = diagnostics if isinstance(diagnostics, dict) else {}

    def safe_float(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
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

    def safe_int(value: Any, default: int = 0) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, number)

    transcript = str(text or "").strip()
    words = re.findall(r"[a-z0-9']+", transcript.lower())
    word_count = len(words)
    char_count = len(transcript)
    confidence_score_raw = diag.get("confidence_score")
    confidence_score = safe_float(confidence_score_raw, -1.0, minimum=-1.0, maximum=1.0)
    if confidence_score < 0.0:
        confidence_score = 0.0
    if confidence_score_raw is None and transcript:
        confidence_score = min(1.0, 0.45 + min(0.4, word_count / 20.0))
    confidence_band = str(diag.get("confidence_band", "")).strip().lower()
    if confidence_band not in {"unknown", "low", "medium", "high"}:
        confidence_band = stt_confidence_band(confidence_score, has_words=word_count > 0)

    payload.update(
        {
            "source": str(source or "none").strip().lower() or "none",
            "fallback_used": bool(fallback_used),
            "confidence_score": confidence_score,
            "confidence_band": confidence_band,
            "avg_logprob": safe_float(diag.get("avg_logprob"), -3.0),
            "avg_no_speech_prob": safe_float(diag.get("avg_no_speech_prob"), 1.0, minimum=0.0, maximum=1.0),
            "language": str(diag.get("language", "unknown")).strip().lower() or "unknown",
            "language_probability": safe_float(diag.get("language_probability"), 0.0, minimum=0.0, maximum=1.0),
            "segment_count": safe_int(diag.get("segment_count", 0)),
            "word_count": word_count if word_count else safe_int(diag.get("word_count", 0)),
            "char_count": char_count if char_count else safe_int(diag.get("char_count", 0)),
            "updated_at": time.time(),
            "error": str(diag.get("error", "")).strip().lower(),
        }
    )
    return payload


def normalize_tts_chunk(
    chunk: np.ndarray,
    *,
    tts_gain: float,
    target_rms: float,
    gain_smooth: float,
) -> tuple[np.ndarray, float]:
    if chunk.size == 0:
        return chunk, tts_gain
    if not np.isfinite(chunk).all():
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=1.0, neginf=-1.0)
    rms = float(np.sqrt(np.mean(chunk**2)))
    if not math.isfinite(rms) or rms <= 1e-6:
        return chunk, tts_gain
    desired_gain = max(0.5, min(2.0, target_rms / rms))
    if not math.isfinite(desired_gain):
        desired_gain = 1.0
    next_gain = tts_gain + ((desired_gain - tts_gain) * gain_smooth)
    normalized = chunk * next_gain
    return np.clip(normalized, -1.0, 1.0), next_gain


def confidence_pause(
    sentence: str,
    *,
    low_confidence_words: set[str],
    confidence_pause_sec: float,
    sentence_pause_sec: float,
    pace: str,
) -> float:
    lowered = sentence.lower()
    if any(token in lowered for token in low_confidence_words):
        pause = confidence_pause_sec
    else:
        pause = sentence_pause_sec
    if pace == "slow":
        return pause * 1.25
    if pace == "fast":
        return pause * 0.8
    return pause


def summarize_tool_error_counters(
    summaries: list[dict[str, Any]],
    *,
    tool_service_error_codes: set[str],
    storage_error_details: set[str],
    service_error_details: set[str],
) -> tuple[float, float, float, dict[str, float]]:
    service_errors = 0.0
    storage_errors = 0.0
    unknown_summary_details = 0.0
    per_code: dict[str, float] = {}
    for item in summaries:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", ""))
        detail = str(item.get("detail", ""))
        if status != "error":
            continue
        if detail in tool_service_error_codes:
            per_code[detail] = per_code.get(detail, 0.0) + 1.0
        if detail in storage_error_details:
            storage_errors += 1.0
            continue
        if detail in service_error_details:
            service_errors += 1.0
            continue
        unknown_summary_details += 1.0
    return (
        service_errors,
        storage_errors,
        unknown_summary_details,
        {name: per_code[name] for name in sorted(per_code)},
    )


def telemetry_snapshot(
    telemetry: dict[str, float],
    *,
    telemetry_error_counts: dict[str, float] | None = None,
) -> dict[str, Any]:
    def metric(key: str) -> float:
        value = telemetry.get(key, 0.0)
        if not math.isfinite(value):
            return 0.0
        return value

    def avg(total_key: str, count_key: str) -> float:
        count = metric(count_key)
        if count <= 0.0:
            return 0.0
        total = metric(total_key)
        value = total / count
        if not math.isfinite(value):
            return 0.0
        return value

    counts = {
        name: value
        for name, value in (telemetry_error_counts or {}).items()
        if math.isfinite(value)
    }
    intent_turns = metric("intent_turns_total")
    answer_total = metric("intent_answer_total")
    completion_total = metric("intent_completion_total")
    answer_success_rate = (
        metric("intent_answer_success") / answer_total if answer_total > 0.0 else 0.0
    )
    completion_success_rate = (
        metric("intent_completion_success") / completion_total
        if completion_total > 0.0
        else 0.0
    )
    correction_frequency = (
        metric("intent_corrections") / intent_turns if intent_turns > 0.0 else 0.0
    )
    return {
        "turns": metric("turns"),
        "barge_ins": metric("barge_ins"),
        "avg_stt_latency_ms": avg("stt_latency_total_ms", "stt_latency_count"),
        "avg_llm_first_sentence_ms": avg(
            "llm_first_sentence_total_ms",
            "llm_first_sentence_count",
        ),
        "avg_tts_first_audio_ms": avg(
            "tts_first_audio_total_ms",
            "tts_first_audio_count",
        ),
        "service_errors": metric("service_errors"),
        "storage_errors": metric("storage_errors"),
        "unknown_summary_details": metric("unknown_summary_details"),
        "service_error_counts": counts,
        "fallback_responses": metric("fallback_responses"),
        "intent_metrics": {
            "turn_count": intent_turns,
            "answer_intent_count": metric("intent_answer_turns"),
            "action_intent_count": metric("intent_action_turns"),
            "hybrid_intent_count": metric("intent_hybrid_turns"),
            "answer_sample_count": answer_total,
            "completion_sample_count": completion_total,
            "answer_quality_success_rate": answer_success_rate,
            "completion_success_rate": completion_success_rate,
            "correction_count": metric("intent_corrections"),
            "correction_frequency": correction_frequency,
            "preference_update_turns": metric("preference_update_turns"),
            "preference_update_fields": metric("preference_update_fields"),
        },
    }
