"""Text-to-Speech using ElevenLabs streaming API.

Uses stream() instead of convert() for lower time-to-first-byte.
Uses eleven_flash_v2_5 model for minimum latency (~75ms TTFB).
Outputs raw PCM int16 at 16kHz for direct playback without codec overhead.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import numpy as np
from typing import AsyncIterator, Iterator

from elevenlabs.client import ElevenLabs

log = logging.getLogger(__name__)


class TextToSpeech:
    """ElevenLabs streaming TTS — low-latency sentence-level synthesis."""

    def __init__(self, api_key: str, voice_id: str, sample_rate: int = 16000):
        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._sample_rate = sample_rate
        self._prev_request_ids: list[str] = []  # for cross-utterance prosody
        log.info("ElevenLabs TTS ready (voice=%s, model=eleven_flash_v2_5)", voice_id)

    def stream_chunks(self, text: str) -> Iterator[np.ndarray]:
        """Stream audio chunks as they arrive from ElevenLabs.

        Yields:
            float32 numpy arrays of PCM audio at self._sample_rate.
            Each chunk is variable-sized (typically 100-500ms of audio).
        """
        if not text or not text.strip():
            return

        try:
            audio_stream = self._client.text_to_speech.stream(
                voice_id=self._voice_id,
                text=text,
                model_id="eleven_flash_v2_5",
                output_format=f"pcm_{self._sample_rate}",
                optimize_streaming_latency=3,
                previous_request_ids=self._prev_request_ids[-3:],
            )

            for chunk in audio_stream:
                if isinstance(chunk, bytes) and len(chunk) > 0:
                    samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                    yield samples

        except Exception as e:
            log.error("TTS synthesis failed: %s", e)

    async def stream_chunks_async(self, text: str) -> AsyncIterator[np.ndarray]:
        """Async wrapper for stream_chunks to avoid blocking the event loop."""
        if not text or not text.strip():
            return

        chunk_queue: "queue.Queue[object]" = queue.Queue()
        sentinel = object()

        def _producer() -> None:
            try:
                for chunk in self.stream_chunks(text):
                    chunk_queue.put(chunk)
            finally:
                chunk_queue.put(sentinel)

        threading.Thread(target=_producer, daemon=True).start()

        while True:
            item = await asyncio.to_thread(chunk_queue.get)
            if item is sentinel:
                break
            yield item  # type: ignore[misc]

    def synthesize(self, text: str) -> np.ndarray:
        """Batch synthesize — collects all chunks into one array.

        Returns:
            float32 numpy array at sample_rate. Empty array on failure.
        """
        if not text or not text.strip():
            return np.array([], dtype=np.float32)

        chunks = list(self.stream_chunks(text))
        if not chunks:
            return np.array([], dtype=np.float32)

        audio = np.concatenate(chunks)
        log.debug("Synthesized %d samples (%.1fs)", len(audio), len(audio) / self._sample_rate)
        return audio
