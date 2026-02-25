"""Audio resilience tests for Jarvis main loop helpers."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from jarvis.__main__ import Jarvis


def test_play_audio_chunk_suppresses_output_write_errors():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._use_robot_audio = False
    jarvis._output_stream = MagicMock()
    jarvis._output_stream.write.side_effect = RuntimeError("device error")

    # Should not raise.
    Jarvis._play_audio_chunk(jarvis, np.ones(32, dtype=np.float32))


def test_normalize_tts_chunk_handles_non_finite_values():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._tts_gain = 1.0

    chunk = np.array([0.1, np.nan, np.inf, -np.inf], dtype=np.float32)
    normalized = Jarvis._normalize_tts_chunk(jarvis, chunk)
    assert np.isfinite(normalized).all()
    assert np.max(np.abs(normalized)) <= 1.0


@pytest.mark.asyncio
async def test_tts_loop_recovers_after_stream_error():
    class FakeTTS:
        async def stream_chunks_async(self, sentence: str):
            if sentence == "bad":
                raise RuntimeError("tts stream failed")
            yield np.ones(16, dtype=np.float32)

    jarvis = Jarvis.__new__(Jarvis)
    jarvis.tts = FakeTTS()
    jarvis._tts_queue = asyncio.Queue()
    jarvis._barge_in = threading.Event()
    jarvis._active_response_id = 1
    jarvis._first_audio_at = None
    jarvis._response_start_at = None
    jarvis._flush_output = MagicMock()
    jarvis._normalize_tts_chunk = lambda x: x
    jarvis._play_audio_chunk = MagicMock()
    jarvis.presence = SimpleNamespace(signals=SimpleNamespace(speech_energy=0.0))

    await jarvis._tts_queue.put((1, "bad", False, 0.0))
    await jarvis._tts_queue.put((1, "good", False, 0.0))

    task = asyncio.create_task(Jarvis._tts_loop(jarvis))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # If the loop survives the first error, it should still process the second sentence.
    assert jarvis._play_audio_chunk.called


@pytest.mark.asyncio
async def test_listen_loop_uses_to_thread_for_input_read():
    class FakeInputStream:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, n: int):
            return np.zeros((n, 1), dtype=np.float32), False

    jarvis = Jarvis.__new__(Jarvis)
    jarvis._use_robot_audio = False
    jarvis.config = SimpleNamespace(sample_rate=16000, doa_change_threshold=0.04, doa_timeout=1.0)
    jarvis.vad = SimpleNamespace(confidence=lambda chunk: 0.0, threshold=0.5, reset=lambda: None)
    jarvis.presence = SimpleNamespace(
        signals=SimpleNamespace(
            vad_energy=0.0,
            doa_angle=None,
            doa_last_seen=None,
            state=None,
            face_last_seen=None,
            hand_last_seen=None,
        )
    )
    jarvis.robot = SimpleNamespace(get_doa=lambda: (None, None))
    jarvis._lock = threading.Lock()
    jarvis._speaking = False
    jarvis._barge_in = threading.Event()
    jarvis._flush_output = MagicMock()
    jarvis._clear_tts_queue = MagicMock()
    jarvis._compute_turn_taking = lambda **kwargs: False
    jarvis._enqueue_utterance = AsyncMock()
    jarvis._last_doa_speech = None
    jarvis._last_doa_angle = None
    jarvis._last_doa_update = 0.0

    async def _fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("jarvis.__main__.sd.InputStream", FakeInputStream), \
         patch("jarvis.__main__.asyncio.to_thread", side_effect=_fake_to_thread) as mock_to_thread:
        task = asyncio.create_task(Jarvis._listen_loop(jarvis))
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert mock_to_thread.called


@pytest.mark.asyncio
async def test_tts_barge_in_soak_harness_stability():
    class FakeTTS:
        async def stream_chunks_async(self, sentence: str):
            # Deterministic short stream for soak testing.
            yield np.ones(8, dtype=np.float32)

    jarvis = Jarvis.__new__(Jarvis)
    jarvis.tts = FakeTTS()
    jarvis._tts_queue = asyncio.Queue()
    jarvis._barge_in = threading.Event()
    jarvis._active_response_id = 1
    jarvis._first_audio_at = None
    jarvis._response_start_at = None
    jarvis._flush_output = MagicMock()
    jarvis._normalize_tts_chunk = lambda x: x
    jarvis._play_audio_chunk = MagicMock()
    jarvis.presence = SimpleNamespace(signals=SimpleNamespace(speech_energy=0.0))
    jarvis._telemetry = {
        "turns": 0.0,
        "barge_ins": 0.0,
        "stt_latency_total_ms": 0.0,
        "stt_latency_count": 0.0,
        "llm_first_sentence_total_ms": 0.0,
        "llm_first_sentence_count": 0.0,
        "tts_first_audio_total_ms": 0.0,
        "tts_first_audio_count": 0.0,
        "service_errors": 0.0,
        "storage_errors": 0.0,
        "fallback_responses": 0.0,
    }

    task = asyncio.create_task(Jarvis._tts_loop(jarvis))
    turns = 60
    for idx in range(turns):
        if idx % 5 == 0:
            jarvis._barge_in.set()
        await jarvis._tts_queue.put((1, f"turn-{idx}", False, 0.0))
        await asyncio.sleep(0.001)
        jarvis._barge_in.clear()

    await asyncio.sleep(0.05)
    assert not task.done()
    assert jarvis._play_audio_chunk.call_count > 0
    assert jarvis._tts_queue.qsize() < turns
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
