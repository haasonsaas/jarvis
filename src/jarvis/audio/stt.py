"""Speech-to-Text using faster-whisper."""

from __future__ import annotations

import logging
import math
import numpy as np
from scipy.signal import resample_poly
from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


class SpeechToText:
    """Local Whisper-based speech recognition."""

    def __init__(self, model_size: str = "base.en"):
        self._model = WhisperModel(model_size, compute_type="int8")
        log.info("Whisper model loaded: %s", model_size)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio to text.

        Args:
            audio: float32 array of shape (samples,) or (samples, channels).
            sample_rate: Audio sample rate (default 16kHz).

        Returns:
            Transcribed text string.
        """
        if audio.size == 0:
            return ""

        if audio.ndim == 2:
            audio = audio.mean(axis=1)  # stereo -> mono

        if sample_rate <= 0:
            log.error("Invalid sample rate for STT: %s", sample_rate)
            return ""

        if sample_rate != 16000:
            g = math.gcd(int(sample_rate), 16000)
            up = 16000 // g
            down = int(sample_rate) // g
            audio = resample_poly(audio.astype(np.float32, copy=False), up=up, down=down).astype(np.float32, copy=False)

        try:
            segments, info = self._model.transcribe(audio, beam_size=5)
            text = " ".join(seg.text.strip() for seg in segments)
        except Exception as e:
            log.error("Transcription failed: %s", e)
            return ""

        if text:
            log.debug("Transcribed: %s", text)

        return text
