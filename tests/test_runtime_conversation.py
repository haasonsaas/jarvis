from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jarvis.presence import State
from jarvis.runtime_conversation import respond_and_speak


@pytest.mark.asyncio
async def test_respond_and_speak_streams_sentences_to_tts_queue() -> None:
    runtime = SimpleNamespace()
    runtime._barge_in = asyncio.Event()
    runtime._clear_tts_queue = MagicMock()
    runtime._response_id = 0
    runtime._active_response_id = 0
    runtime._response_started = False
    runtime._first_sentence_at = None
    runtime._first_audio_at = None
    runtime._response_start_at = None
    runtime._tts_gain = 1.0
    runtime._filler_task = None
    runtime.tts = object()
    runtime._thinking_filler = MagicMock(return_value=asyncio.sleep(3600))
    runtime._lock = threading.Lock()
    runtime._speaking = False
    runtime._telemetry = {
        "llm_first_sentence_total_ms": 0.0,
        "llm_first_sentence_count": 0.0,
    }
    runtime._tts_queue = asyncio.Queue()
    runtime._confidence_pause = lambda sentence: 0.0
    runtime._flush_output = MagicMock()
    runtime.robot = SimpleNamespace(stop_sequence=MagicMock())
    runtime.presence = SimpleNamespace(signals=SimpleNamespace(state=State.THINKING))
    runtime._voice_controller = lambda: SimpleNamespace(continue_listening=MagicMock())
    runtime._publish_voice_status = MagicMock()

    async def _responses():
        yield "First sentence"

    runtime.brain = SimpleNamespace(respond=lambda _: _responses())

    await respond_and_speak(runtime, "hello")

    queued = runtime._tts_queue.get_nowait()
    assert queued[1] == "First sentence"
    assert runtime._response_started is True
    assert runtime._telemetry["llm_first_sentence_count"] == 1.0
    runtime._publish_voice_status.assert_called_once()


@pytest.mark.asyncio
async def test_respond_and_speak_honors_barge_in_mid_stream() -> None:
    runtime = SimpleNamespace()
    runtime._barge_in = asyncio.Event()
    runtime._clear_tts_queue = MagicMock()
    runtime._response_id = 0
    runtime._active_response_id = 0
    runtime._response_started = False
    runtime._first_sentence_at = None
    runtime._first_audio_at = None
    runtime._response_start_at = None
    runtime._tts_gain = 1.0
    runtime._filler_task = None
    runtime.tts = object()
    runtime._thinking_filler = MagicMock(return_value=asyncio.sleep(3600))
    runtime._lock = threading.Lock()
    runtime._speaking = False
    runtime._telemetry = {
        "llm_first_sentence_total_ms": 0.0,
        "llm_first_sentence_count": 0.0,
    }
    runtime._tts_queue = asyncio.Queue()
    runtime._confidence_pause = lambda sentence: 0.0
    runtime._flush_output = MagicMock()
    runtime.robot = SimpleNamespace(stop_sequence=MagicMock())
    runtime.presence = SimpleNamespace(signals=SimpleNamespace(state=State.THINKING))
    runtime._voice_controller = lambda: SimpleNamespace(continue_listening=MagicMock())
    runtime._publish_voice_status = MagicMock()

    async def _responses():
        yield "First sentence"
        runtime._barge_in.set()
        yield "Second sentence"

    runtime.brain = SimpleNamespace(respond=lambda _: _responses())

    await respond_and_speak(runtime, "hello")

    queued = runtime._tts_queue.get_nowait()
    assert queued[1] == "First sentence"
    runtime._flush_output.assert_called_once()
    runtime.robot.stop_sequence.assert_called_once()
