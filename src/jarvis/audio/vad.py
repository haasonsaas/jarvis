"""Voice Activity Detection using Silero VAD.

Uses the pip package (silero-vad) with VADIterator for streaming detection.
Chunk size is fixed at 512 samples (32ms) at 16kHz — this is a hard
requirement of the Silero model and cannot be changed.
"""

from __future__ import annotations

import logging
import numpy as np
import torch

from silero_vad import load_silero_vad, VADIterator

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512  # exactly 32ms at 16kHz — required by Silero


class VoiceActivityDetector:
    """Silero VAD wrapper for streaming speech detection."""

    def __init__(self, threshold: float = 0.5, sample_rate: int = SAMPLE_RATE):
        if sample_rate != 16000:
            raise ValueError("Silero VAD requires 16kHz audio")

        torch.set_num_threads(1)  # small model, threading overhead hurts
        self._model = load_silero_vad()
        self._sample_rate = sample_rate
        self._threshold = threshold

        # VADIterator handles start/end detection with hysteresis
        self._iterator = VADIterator(
            self._model,
            threshold=threshold,
            sampling_rate=sample_rate,
            min_silence_duration_ms=100,
            speech_pad_ms=30,
        )
        log.info("Silero VAD loaded (threshold=%.2f)", threshold)

    @property
    def threshold(self) -> float:
        return self._threshold

    def confidence(self, audio_chunk: np.ndarray) -> float:
        """Return speech confidence for a single 512-sample chunk."""
        if audio_chunk.ndim == 2:
            audio_chunk = audio_chunk.mean(axis=1)

        if len(audio_chunk) != CHUNK_SAMPLES:
            raise ValueError(
                f"Chunk must be exactly {CHUNK_SAMPLES} samples, got {len(audio_chunk)}"
            )

        tensor = torch.from_numpy(audio_chunk).float()
        return float(self._model(tensor, self._sample_rate).item())

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Check if a 512-sample audio chunk contains speech.

        Args:
            audio_chunk: float32 array of exactly 512 samples at 16kHz mono.
        """
        return self.confidence(audio_chunk) > self._threshold

    def detect_boundaries(self, audio_chunk: np.ndarray) -> dict | None:
        """Feed a chunk to VADIterator for start/end-of-speech detection.

        Returns:
            {"start": sample_index} when speech begins,
            {"end": sample_index} when speech ends,
            None when state is unchanged.
        """
        if audio_chunk.ndim == 2:
            audio_chunk = audio_chunk.mean(axis=1)

        tensor = torch.from_numpy(audio_chunk).float()
        return self._iterator(tensor, return_seconds=False)

    def reset(self) -> None:
        """Reset internal state between utterances."""
        self._iterator.reset_states()
        self._model.reset_states()
