"""Lifecycle robustness tests for jarvis.__main__.Jarvis."""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

from jarvis.__main__ import Jarvis


def test_stop_is_noop_when_not_started():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._started = False
    Jarvis.stop(jarvis)  # should not raise


def test_stop_suppresses_component_errors_and_resets_started():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._started = True
    jarvis._output_stream = MagicMock()
    jarvis._output_stream.stop.side_effect = RuntimeError("stream stop failed")
    jarvis._output_stream.close.side_effect = RuntimeError("stream close failed")
    jarvis.face_tracker = MagicMock()
    jarvis.face_tracker.stop.side_effect = RuntimeError("face stop failed")
    jarvis.hand_tracker = MagicMock()
    jarvis.hand_tracker.stop.side_effect = RuntimeError("hand stop failed")
    jarvis._use_robot_audio = True
    jarvis.robot = MagicMock()
    jarvis.robot.stop_audio.side_effect = RuntimeError("audio stop failed")
    jarvis.robot.disconnect.side_effect = RuntimeError("disconnect failed")
    jarvis.presence = MagicMock()
    jarvis.presence.stop.side_effect = RuntimeError("presence stop failed")
    jarvis.config = SimpleNamespace(motion_enabled=True)

    Jarvis.stop(jarvis)
    assert jarvis._started is False
    assert jarvis._output_stream is None
    assert jarvis.face_tracker is None
    assert jarvis.hand_tracker is None


@pytest.mark.asyncio
async def test_run_cleans_up_when_start_fails():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis.start = MagicMock(side_effect=RuntimeError("start failed"))
    jarvis.stop = MagicMock()
    jarvis._listen_task = None
    jarvis._tts_task = None
    jarvis._filler_task = None
    jarvis.brain = MagicMock()
    jarvis.brain.close = AsyncMock()

    with pytest.raises(RuntimeError):
        await Jarvis.run(jarvis)

    jarvis.brain.close.assert_awaited_once()
    jarvis.stop.assert_called_once()
