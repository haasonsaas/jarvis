"""Audio-output runtime helpers for TTS playback and barge-in behavior."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any, Callable

import numpy as np


def flush_output(runtime: Any) -> None:
    if runtime._use_robot_audio:
        runtime.robot.flush_audio_output()
        return

    if runtime._output_stream is None:
        return

    try:
        runtime._output_stream.abort()
    except Exception:
        try:
            runtime._output_stream.stop()
        except Exception:
            pass

    try:
        runtime._output_stream.start()
    except Exception:
        pass


def play_audio_chunk(
    runtime: Any,
    audio_16k: np.ndarray,
    *,
    resample_audio_fn: Callable[[np.ndarray, int, int], np.ndarray],
    logger: Any,
) -> None:
    if audio_16k.size == 0:
        return

    if runtime._use_robot_audio:
        audio_out = audio_16k
        if runtime._robot_output_sr != runtime.config.sample_rate:
            audio_out = resample_audio_fn(audio_16k, runtime.config.sample_rate, runtime._robot_output_sr)
        runtime.robot.push_audio_sample(audio_out)
        return

    if runtime._output_stream is not None:
        try:
            runtime._output_stream.write(audio_16k.reshape(-1, 1))
        except Exception as exc:
            logger.warning("Audio output write failed: %s", exc)


def clear_tts_queue(runtime: Any) -> None:
    while not runtime._tts_queue.empty():
        try:
            runtime._tts_queue.get_nowait()
        except asyncio.QueueEmpty:
            break


async def tts_loop(runtime: Any, *, logger: Any) -> None:
    """Consume queued sentences and stream TTS audio with barge-in handling."""
    assert runtime.tts is not None
    while True:
        response_id, sentence, is_filler, pause = await runtime._tts_queue.get()
        if runtime._barge_in.is_set():
            runtime._flush_output()
            runtime.presence.signals.speech_energy = 0.0
            continue

        if not getattr(runtime, "_tts_output_enabled", True):
            if not is_filler:
                print(f"  JARVIS: {sentence}")
            if pause > 0:
                await asyncio.sleep(pause)
            continue

        try:
            async for audio_chunk in runtime.tts.stream_chunks_async(sentence):
                if runtime._barge_in.is_set():
                    runtime._flush_output()
                    runtime.presence.signals.speech_energy = 0.0
                    break
                if not is_filler and response_id == runtime._active_response_id and runtime._first_audio_at is None:
                    runtime._first_audio_at = time.monotonic()
                    if runtime._response_start_at is not None:
                        latency_ms = (runtime._first_audio_at - runtime._response_start_at) * 1000.0
                        runtime._telemetry["tts_first_audio_total_ms"] += latency_ms
                        runtime._telemetry["tts_first_audio_count"] += 1.0
                        logger.info(
                            "TTS first audio latency: %.0fms",
                            latency_ms,
                        )
                runtime.presence.signals.speech_energy = float(
                    max(0.0, min(1.0, float(np.sqrt(np.mean(audio_chunk ** 2)) * 5.0)))
                )
                normalized = runtime._normalize_tts_chunk(audio_chunk)
                runtime._play_audio_chunk(normalized)
                await asyncio.sleep(0)
        except Exception as exc:
            logger.warning("TTS loop failed for sentence chunk: %s", exc)
            config = getattr(runtime, "config", None)
            if bool(getattr(config, "tts_fallback_text_only", True)) and not is_filler:
                print(f"  JARVIS: {sentence}")
                telemetry = getattr(runtime, "_telemetry", None)
                if isinstance(telemetry, dict):
                    telemetry["fallback_responses"] = float(telemetry.get("fallback_responses", 0.0) or 0.0) + 1.0
                observability = getattr(runtime, "_observability", None)
                if observability is not None:
                    with suppress(Exception):
                        observability.record_event(
                            "tts_fallback_text_only",
                            {"sentence_len": len(sentence)},
                        )
        runtime.presence.signals.speech_energy = 0.0
        if pause > 0:
            await asyncio.sleep(pause)
