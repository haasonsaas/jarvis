"""Audio resilience tests for Jarvis main loop helpers."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

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
