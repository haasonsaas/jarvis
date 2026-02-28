from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.presence import State
from jarvis.runtime_conversation import _semantic_turn_should_commit, respond_and_speak


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
        "llm_prompt_tokens_total": 0.0,
        "llm_completion_tokens_total": 0.0,
        "llm_total_tokens_total": 0.0,
        "llm_cost_usd_total": 0.0,
        "llm_usage_samples": 0.0,
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

    runtime.brain = SimpleNamespace(
        respond=lambda _: _responses(),
        latest_llm_usage=lambda: {
            "prompt_tokens": 120,
            "completion_tokens": 80,
            "total_tokens": 200,
            "cost_usd": 0.04,
        },
    )

    await respond_and_speak(runtime, "hello")

    queued = runtime._tts_queue.get_nowait()
    assert queued[1] == "First sentence"
    assert runtime._response_started is True
    assert runtime._telemetry["llm_first_sentence_count"] == 1.0
    assert runtime._telemetry["llm_total_tokens_total"] == 200.0
    assert runtime._telemetry["llm_usage_samples"] == 1.0
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


@pytest.mark.asyncio
async def test_semantic_turn_should_commit_returns_true_when_disabled() -> None:
    runtime = SimpleNamespace(
        config=SimpleNamespace(semantic_turn_enabled=False),
        _telemetry={},
    )
    decision = await _semantic_turn_should_commit(
        runtime,
        audio=np.ones(32, dtype=np.float32),
        assistant_busy=False,
        silence_elapsed_sec=0.9,
        utterance_duration_sec=1.2,
    )
    assert decision is True


@pytest.mark.asyncio
async def test_semantic_turn_should_commit_respects_brain_wait_decision() -> None:
    class _Brain:
        async def semantic_turn_decision(self, **_kwargs):
            return SimpleNamespace(action="wait", route_confidence=0.9)

        def latest_semantic_turn_trace(self):
            return {
                "action": "wait",
                "route_confidence": 0.9,
                "route_source": "router",
            }

    runtime = SimpleNamespace(
        config=SimpleNamespace(
            semantic_turn_enabled=True,
            semantic_turn_max_transcript_chars=220,
        ),
        brain=_Brain(),
        _transcribe_with_fallback=lambda _audio: "turn on the office and",
        _telemetry={
            "semantic_turn_decisions_total": 0.0,
            "semantic_turn_waits": 0.0,
            "semantic_turn_commits": 0.0,
            "semantic_turn_fallbacks": 0.0,
        },
        _last_semantic_turn_route={},
    )
    decision = await _semantic_turn_should_commit(
        runtime,
        audio=np.ones(32, dtype=np.float32),
        assistant_busy=False,
        silence_elapsed_sec=0.85,
        utterance_duration_sec=1.15,
    )
    assert decision is False
    assert runtime._telemetry["semantic_turn_decisions_total"] == 1.0
    assert runtime._telemetry["semantic_turn_waits"] == 1.0
    assert runtime._last_semantic_turn_route["action"] == "wait"
