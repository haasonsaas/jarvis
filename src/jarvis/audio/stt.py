"""Speech-to-Text using faster-whisper."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
from scipy.signal import resample_poly
from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


def _tokenize_words(text: str) -> list[str]:
    chars: list[str] = []
    for ch in str(text or "").lower():
        chars.append(ch if (ch.isalnum() or ch == "'") else " ")
    return [token for token in "".join(chars).split() if token]


class SpeechToText:
    """Local Whisper-based speech recognition."""

    def __init__(self, model_size: str = "base.en"):
        self._model = WhisperModel(model_size, compute_type="int8")
        log.info("Whisper model loaded: %s", model_size)

    @staticmethod
    def _clamp01(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return max(0.0, min(1.0, value))

    @staticmethod
    def _finite_float(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return number

    @classmethod
    def _estimate_confidence(
        cls,
        *,
        avg_logprob: float,
        avg_no_speech_prob: float,
        language_probability: float,
        word_count: int,
    ) -> float:
        # avg_logprob is typically in [-2.5, 0.0] for usable transcripts.
        logprob_score = cls._clamp01((avg_logprob + 2.5) / 2.5)
        speech_score = 1.0 - cls._clamp01(avg_no_speech_prob)
        language_score = cls._clamp01(language_probability)
        length_score = cls._clamp01(float(word_count) / 8.0)
        score = (
            (0.55 * logprob_score)
            + (0.25 * speech_score)
            + (0.10 * language_score)
            + (0.10 * length_score)
        )
        if word_count <= 0:
            score *= 0.2
        return cls._clamp01(score)

    @staticmethod
    def _confidence_band(score: float, *, has_words: bool) -> str:
        if not has_words:
            return "unknown"
        if score >= 0.78:
            return "high"
        if score >= 0.50:
            return "medium"
        return "low"

    def transcribe_with_diagnostics(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> tuple[str, dict[str, Any]]:
        diagnostics: dict[str, Any] = {
            "confidence_score": 0.0,
            "confidence_band": "unknown",
            "avg_logprob": -3.0,
            "avg_no_speech_prob": 1.0,
            "language": "unknown",
            "language_probability": 0.0,
            "segment_count": 0,
            "word_count": 0,
            "char_count": 0,
            "error": "",
        }
        if audio.size == 0:
            diagnostics["error"] = "empty_audio"
            return "", diagnostics

        if audio.ndim == 2:
            audio = audio.mean(axis=1)  # stereo -> mono

        if sample_rate <= 0:
            log.error("Invalid sample rate for STT: %s", sample_rate)
            diagnostics["error"] = "invalid_sample_rate"
            return "", diagnostics

        if sample_rate != 16000:
            g = math.gcd(int(sample_rate), 16000)
            up = 16000 // g
            down = int(sample_rate) // g
            audio = resample_poly(audio.astype(np.float32, copy=False), up=up, down=down).astype(np.float32, copy=False)

        try:
            segments_iter, info = self._model.transcribe(audio, beam_size=5)
            segments = list(segments_iter)
        except Exception as e:
            log.error("Transcription failed: %s", e)
            diagnostics["error"] = "transcription_failed"
            return "", diagnostics

        text = " ".join(seg.text.strip() for seg in segments if str(getattr(seg, "text", "")).strip()).strip()
        words = _tokenize_words(text)
        logprob_values = [
            self._finite_float(getattr(seg, "avg_logprob", None), default=-3.0)
            for seg in segments
            if math.isfinite(self._finite_float(getattr(seg, "avg_logprob", None), default=float("nan")))
        ]
        no_speech_values = [
            self._finite_float(getattr(seg, "no_speech_prob", None), default=1.0)
            for seg in segments
            if math.isfinite(self._finite_float(getattr(seg, "no_speech_prob", None), default=float("nan")))
        ]
        avg_logprob = sum(logprob_values) / len(logprob_values) if logprob_values else -3.0
        avg_no_speech_prob = sum(no_speech_values) / len(no_speech_values) if no_speech_values else 1.0
        language = str(getattr(info, "language", "")).strip().lower() or "unknown"
        language_probability = self._clamp01(self._finite_float(getattr(info, "language_probability", 0.0), default=0.0))
        confidence_score = self._estimate_confidence(
            avg_logprob=avg_logprob,
            avg_no_speech_prob=avg_no_speech_prob,
            language_probability=language_probability,
            word_count=len(words),
        )
        diagnostics.update(
            {
                "confidence_score": confidence_score,
                "confidence_band": self._confidence_band(confidence_score, has_words=bool(words)),
                "avg_logprob": avg_logprob,
                "avg_no_speech_prob": self._clamp01(avg_no_speech_prob),
                "language": language,
                "language_probability": language_probability,
                "segment_count": len(segments),
                "word_count": len(words),
                "char_count": len(text),
            }
        )

        if text:
            log.debug("Transcribed: %s", text)

        return text, diagnostics

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio to text."""
        text, _ = self.transcribe_with_diagnostics(audio, sample_rate=sample_rate)
        return text
