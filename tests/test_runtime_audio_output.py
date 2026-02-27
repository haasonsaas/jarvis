from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.runtime_audio_output import (
    clear_tts_queue,
    flush_output,
    play_audio_chunk,
    tts_loop,
)


def test_flush_output_uses_robot_audio_path() -> None:
    robot = SimpleNamespace(flush_audio_output=MagicMock())
    runtime = SimpleNamespace(
        _use_robot_audio=True,
        robot=robot,
        _output_stream=None,
    )

    flush_output(runtime)
    robot.flush_audio_output.assert_called_once()


def test_flush_output_recovers_local_stream_abort_failure() -> None:
    stream = MagicMock()
    stream.abort.side_effect = RuntimeError("abort failed")
    runtime = SimpleNamespace(
        _use_robot_audio=False,
        robot=SimpleNamespace(flush_audio_output=MagicMock()),
        _output_stream=stream,
    )

    flush_output(runtime)
    stream.stop.assert_called_once()
    stream.start.assert_called_once()


def test_play_audio_chunk_resamples_before_robot_push() -> None:
    input_audio = np.ones(8, dtype=np.float32)
    output_audio = np.ones(4, dtype=np.float32)
    robot = SimpleNamespace(push_audio_sample=MagicMock())
    runtime = SimpleNamespace(
        _use_robot_audio=True,
        _robot_output_sr=24000,
        config=SimpleNamespace(sample_rate=16000),
        robot=robot,
        _output_stream=None,
    )
    resample_audio = MagicMock(return_value=output_audio)
    logger = SimpleNamespace(warning=MagicMock())

    play_audio_chunk(
        runtime,
        input_audio,
        resample_audio_fn=resample_audio,
        logger=logger,
    )

    resample_audio.assert_called_once_with(input_audio, 16000, 24000)
    robot.push_audio_sample.assert_called_once_with(output_audio)


def test_play_audio_chunk_swallows_output_stream_errors() -> None:
    stream = MagicMock()
    stream.write.side_effect = RuntimeError("write failed")
    logger = SimpleNamespace(warning=MagicMock())
    runtime = SimpleNamespace(
        _use_robot_audio=False,
        _output_stream=stream,
        config=SimpleNamespace(sample_rate=16000),
        _robot_output_sr=16000,
        robot=SimpleNamespace(push_audio_sample=MagicMock()),
    )

    play_audio_chunk(
        runtime,
        np.ones(10, dtype=np.float32),
        resample_audio_fn=lambda audio, _in, _out: audio,
        logger=logger,
    )

    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_clear_tts_queue_drains_items() -> None:
    runtime = SimpleNamespace(_tts_queue=asyncio.Queue())
    await runtime._tts_queue.put((1, "a", False, 0.0))
    await runtime._tts_queue.put((1, "b", False, 0.0))

    clear_tts_queue(runtime)
    assert runtime._tts_queue.empty()


@pytest.mark.asyncio
async def test_tts_loop_fallback_records_telemetry_and_observability() -> None:
    class _FailingTTS:
        async def stream_chunks_async(self, _sentence: str):
            raise RuntimeError("boom")
            yield np.ones(2, dtype=np.float32)  # pragma: no cover

    observability = SimpleNamespace(record_event=MagicMock())
    logger = SimpleNamespace(info=MagicMock(), warning=MagicMock())
    runtime = SimpleNamespace(
        tts=_FailingTTS(),
        _tts_queue=asyncio.Queue(),
        _barge_in=threading.Event(),
        _active_response_id=1,
        _first_audio_at=None,
        _response_start_at=None,
        _flush_output=MagicMock(),
        _normalize_tts_chunk=lambda x: x,
        _play_audio_chunk=MagicMock(),
        presence=SimpleNamespace(signals=SimpleNamespace(speech_energy=0.0)),
        config=SimpleNamespace(tts_fallback_text_only=True),
        _telemetry={"fallback_responses": 0.0},
        _observability=observability,
        _tts_output_enabled=True,
    )

    await runtime._tts_queue.put((1, "hello", False, 0.0))
    task = asyncio.create_task(tts_loop(runtime, logger=logger))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runtime._telemetry["fallback_responses"] == 1.0
    assert runtime.presence.signals.speech_energy == 0.0
    observability.record_event.assert_called_once()
