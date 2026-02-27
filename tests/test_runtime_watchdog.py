from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jarvis.presence import State
from jarvis.runtime_watchdog import watchdog_loop


@pytest.mark.asyncio
async def test_watchdog_loop_resets_stuck_state_and_records_event() -> None:
    observability = SimpleNamespace(record_event=MagicMock())
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            watchdog_listening_timeout_sec=0.05,
            watchdog_thinking_timeout_sec=0.05,
            watchdog_speaking_timeout_sec=0.05,
        ),
        presence=SimpleNamespace(signals=SimpleNamespace(state=State.THINKING)),
        _runtime_invariant_checked_monotonic=0.0,
        _check_runtime_invariants=MagicMock(),
        _barge_in=threading.Event(),
        _flush_output=MagicMock(),
        _clear_tts_queue=MagicMock(),
        _telemetry={"fallback_responses": 0.0},
        _observability=observability,
    )

    task = asyncio.create_task(
        watchdog_loop(
            runtime,
            state_idle=State.IDLE,
            state_listening=State.LISTENING,
            state_thinking=State.THINKING,
            state_speaking=State.SPEAKING,
            poll_sec=0.01,
            logger=SimpleNamespace(warning=MagicMock()),
        )
    )
    await asyncio.sleep(0.09)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runtime.presence.signals.state == State.IDLE
    assert runtime._flush_output.called
    assert runtime._clear_tts_queue.called
    assert runtime._telemetry["fallback_responses"] >= 1.0
    observability.record_event.assert_called()
    runtime._check_runtime_invariants.assert_called()
