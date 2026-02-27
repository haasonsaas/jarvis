"""Watchdog loop runtime helper."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any


async def watchdog_loop(
    runtime: Any,
    *,
    state_idle: Any,
    state_listening: Any,
    state_thinking: Any,
    state_speaking: Any,
    poll_sec: float,
    logger: Any,
) -> None:
    state_name = str(getattr(runtime.presence.signals.state, "value", "unknown")).lower()
    state_since = time.monotonic()
    while True:
        now = time.monotonic()
        if (now - float(getattr(runtime, "_runtime_invariant_checked_monotonic", 0.0))) >= 2.0:
            with suppress(Exception):
                runtime._check_runtime_invariants(auto_heal=True)
        current = str(getattr(runtime.presence.signals.state, "value", "unknown")).lower()
        if current != state_name:
            state_name = current
            state_since = now
        timeout = None
        if current == str(state_listening.value):
            timeout = runtime.config.watchdog_listening_timeout_sec
        elif current == str(state_thinking.value):
            timeout = runtime.config.watchdog_thinking_timeout_sec
        elif current == str(state_speaking.value):
            timeout = runtime.config.watchdog_speaking_timeout_sec
        if timeout is not None and (now - state_since) > timeout:
            logger.warning("Watchdog reset triggered for state=%s", current)
            runtime.presence.signals.state = state_idle
            runtime._barge_in.set()
            runtime._flush_output()
            runtime._clear_tts_queue()
            runtime._barge_in.clear()
            runtime._telemetry["fallback_responses"] += 1.0
            observability = getattr(runtime, "_observability", None)
            if observability is not None:
                with suppress(Exception):
                    observability.record_event(
                        "watchdog_reset",
                        {"state": current, "timeout_sec": timeout},
                    )
            state_name = str(state_idle.value)
            state_since = now
        await asyncio.sleep(poll_sec)
