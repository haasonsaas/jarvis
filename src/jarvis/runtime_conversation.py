"""Conversation loop helpers extracted from Jarvis main runtime."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from contextlib import suppress
from typing import Any, Callable

import numpy as np

from jarvis.presence import State
from jarvis.runtime_constants import (
    CONFIRMATION_PHRASE,
    REPAIR_REPEAT_PROMPT,
    TELEMETRY_LOG_EVERY_TURNS,
)
from jarvis.tools import services as service_tools

log = logging.getLogger(__name__)


async def run(runtime: Any) -> None:
    """Main conversation loop."""
    try:
        runtime.start()
        if runtime.tts is not None:
            runtime._tts_task = asyncio.create_task(runtime._tts_loop(), name="tts")
        runtime._listen_task = asyncio.create_task(runtime._listen_loop(), name="listen")
        if runtime.config.watchdog_enabled:
            runtime._watchdog_task = asyncio.create_task(
                runtime._watchdog_loop(),
                name="watchdog",
            )
        await runtime._start_operator_server()
        print("\n  JARVIS is online. Speak to begin.\n")
        print("  Press Ctrl+C to exit.\n")
        for line in runtime._startup_summary_lines():
            print(f"  {line}")
        for warning in getattr(runtime.config, "startup_warnings", []):
            print(f"  WARNING: {warning}")
        print("")

        while True:
            utterance = await runtime._utterance_queue.get()

            runtime.presence.signals.state = State.THINKING
            text = await asyncio.get_event_loop().run_in_executor(
                None,
                runtime._transcribe_with_fallback,
                utterance,
            )
            stt_elapsed = (
                time.monotonic() - runtime._last_doa_update
                if runtime._last_doa_update
                else None
            )
            stt_latency_ms = (
                (stt_elapsed * 1000.0) if stt_elapsed is not None else None
            )
            if stt_elapsed is not None:
                log.info("STT latency: %.0fms", stt_elapsed * 1000.0)
                runtime._telemetry["stt_latency_total_ms"] += stt_elapsed * 1000.0
                runtime._telemetry["stt_latency_count"] += 1.0
            runtime._publish_voice_status()
            if not text.strip():
                runtime.presence.signals.state = State.IDLE
                runtime._publish_voice_status()
                continue

            decision = runtime._voice_controller().process_transcript(text)
            if decision.reply:
                if runtime.tts:
                    await runtime._tts_queue.put(
                        (runtime._active_response_id, decision.reply, True, 0.0)
                    )
                else:
                    print(f"  JARVIS: {decision.reply}")
            if not decision.accepted:
                runtime.presence.signals.state = State.IDLE
                runtime._publish_voice_status()
                continue
            text = decision.text
            utterance_duration_sec = float(len(utterance)) / float(runtime.config.sample_rate)
            turn_count = max(1.0, float(runtime._telemetry.get("turns", 0.0)))
            interruption_likelihood = (
                float(runtime._telemetry.get("barge_ins", 0.0)) / turn_count
            )
            runtime._voice_controller().register_utterance(
                text,
                duration_sec=utterance_duration_sec,
                interruption_likelihood=interruption_likelihood,
            )

            repair_resolved_this_turn = False
            if runtime._awaiting_confirmation:
                normalized = text.strip().lower()
                intent = runtime._voice_controller().confirmation_intent(normalized)
                if intent == "confirm" and runtime._pending_text:
                    runtime._awaiting_confirmation = False
                    text = runtime._pending_text
                    runtime._pending_text = None
                elif intent == "deny":
                    runtime._awaiting_confirmation = False
                    runtime._pending_text = None
                    if runtime.tts:
                        await runtime._tts_queue.put(
                            (runtime._active_response_id, "Understood.", True, 0.0)
                        )
                    else:
                        print("  JARVIS: Understood.")
                    runtime.presence.signals.state = State.IDLE
                    runtime._publish_voice_status()
                    continue
                elif intent == "repeat":
                    if runtime.tts:
                        await runtime._tts_queue.put(
                            (
                                runtime._active_response_id,
                                "Please say confirm to proceed or deny to cancel.",
                                True,
                                0.0,
                            )
                        )
                    else:
                        print(
                            "  JARVIS: Please say confirm to proceed or deny to cancel."
                        )
                    runtime.presence.signals.state = State.LISTENING
                    runtime._awaiting_confirmation = True
                    runtime._publish_voice_status()
                    continue
                else:
                    runtime._awaiting_confirmation = False
                    runtime._pending_text = None

            if runtime._awaiting_repair_confirmation:
                normalized = text.strip().lower()
                intent = runtime._voice_controller().confirmation_intent(normalized)
                words = re.findall(r"[a-z0-9']+", normalized)
                if intent == "confirm" and runtime._repair_candidate_text:
                    text = runtime._repair_candidate_text
                    runtime._awaiting_repair_confirmation = False
                    runtime._repair_candidate_text = None
                    repair_resolved_this_turn = True
                elif intent in {"deny", "repeat"} and len(words) <= 2:
                    if runtime.tts:
                        await runtime._tts_queue.put(
                            (
                                runtime._active_response_id,
                                REPAIR_REPEAT_PROMPT,
                                True,
                                0.0,
                            )
                        )
                    else:
                        print(f"  JARVIS: {REPAIR_REPEAT_PROMPT}")
                    runtime.presence.signals.state = State.LISTENING
                    runtime._awaiting_repair_confirmation = True
                    runtime._publish_voice_status()
                    continue
                else:
                    runtime._awaiting_repair_confirmation = False
                    runtime._repair_candidate_text = None
                    repair_resolved_this_turn = True

            intent_class = runtime._classify_user_intent(text)
            runtime._telemetry["intent_turns_total"] += 1.0
            if intent_class == "action":
                runtime._telemetry["intent_action_turns"] += 1.0
            elif intent_class == "hybrid":
                runtime._telemetry["intent_hybrid_turns"] += 1.0
            else:
                runtime._telemetry["intent_answer_turns"] += 1.0
            looks_like_correction = runtime._looks_like_user_correction(text)
            if looks_like_correction:
                runtime._telemetry["intent_corrections"] += 1.0

            turn_started_at = time.time()
            learned_preferences: dict[str, str] = {}
            if hasattr(runtime, "_learn_voice_preferences"):
                try:
                    learned_preferences = runtime._learn_voice_preferences(
                        text,
                        now_ts=turn_started_at,
                    )
                except Exception:
                    learned_preferences = {}
            if (
                not repair_resolved_this_turn
                and runtime._requires_stt_repair(text, intent_class)
            ):
                runtime._awaiting_repair_confirmation = True
                runtime._repair_candidate_text = text
                prompt = runtime._repair_prompt(text)
                if runtime.tts:
                    await runtime._tts_queue.put(
                        (runtime._active_response_id, prompt, True, 0.0)
                    )
                else:
                    print(f"  JARVIS: {prompt}")
                runtime.presence.signals.state = State.LISTENING
                runtime._publish_voice_status()
                runtime._record_conversation_trace(
                    user_text=text,
                    intent_class=intent_class,
                    turn_started_at=turn_started_at,
                    stt_latency_ms=stt_latency_ms,
                    llm_first_sentence_ms=0.0,
                    tts_first_audio_ms=0.0,
                    response_success=None,
                    tool_summaries=[],
                    lifecycle="repair_requested",
                    used_brain_response=False,
                    followup_carryover_applied=False,
                )
                continue

            memory_correction = runtime._parse_memory_correction_command(text)
            if memory_correction is not None:
                tool_name, payload = memory_correction
                if tool_name == "memory_forget":
                    result = await service_tools.memory_forget(payload)
                else:
                    result = await service_tools.memory_update(payload)
                if not looks_like_correction:
                    runtime._telemetry["intent_corrections"] += 1.0
                turn_tool_summaries = runtime._turn_tool_summaries_since(turn_started_at)
                completion_outcome = runtime._completion_success_from_summaries(
                    turn_tool_summaries
                )
                if completion_outcome is not None:
                    runtime._telemetry["intent_completion_total"] += 1.0
                    if completion_outcome:
                        runtime._telemetry["intent_completion_success"] += 1.0
                correction_succeeded = not bool(result.get("isError", False))
                runtime._update_followup_carryover(
                    text,
                    intent_class,
                    resolved=correction_succeeded,
                    now_ts=turn_started_at,
                )
                reply = (
                    str(result.get("content", [{}])[0].get("text", "")).strip()
                    or "Done."
                )
                if runtime.tts:
                    await runtime._tts_queue.put(
                        (runtime._active_response_id, reply, True, 0.0)
                    )
                else:
                    print(f"  JARVIS: {reply}")
                runtime.presence.signals.state = State.IDLE
                runtime._publish_voice_status()
                runtime._record_conversation_trace(
                    user_text=text,
                    intent_class=intent_class,
                    turn_started_at=turn_started_at,
                    stt_latency_ms=stt_latency_ms,
                    llm_first_sentence_ms=0.0,
                    tts_first_audio_ms=0.0,
                    response_success=True,
                    tool_summaries=turn_tool_summaries,
                    lifecycle="memory_correction",
                    used_brain_response=False,
                    followup_carryover_applied=False,
                )
                continue

            if runtime._requires_confirmation(time.monotonic()):
                runtime._awaiting_confirmation = True
                runtime._pending_text = text
                runtime._telemetry["fallback_responses"] += 1.0
                runtime._update_followup_carryover(
                    text,
                    intent_class,
                    resolved=False,
                    now_ts=turn_started_at,
                )
                if runtime.tts:
                    await runtime._tts_queue.put(
                        (
                            runtime._active_response_id,
                            CONFIRMATION_PHRASE,
                            True,
                            0.0,
                        )
                    )
                else:
                    print(f"  JARVIS: {CONFIRMATION_PHRASE}")
                runtime.presence.signals.state = State.LISTENING
                runtime._publish_voice_status()
                runtime._record_conversation_trace(
                    user_text=text,
                    intent_class=intent_class,
                    turn_started_at=turn_started_at,
                    stt_latency_ms=stt_latency_ms,
                    llm_first_sentence_ms=0.0,
                    tts_first_audio_ms=0.0,
                    response_success=None,
                    tool_summaries=[],
                    lifecycle="confirmation_requested",
                    used_brain_response=False,
                    followup_carryover_applied=False,
                )
                continue

            runtime._telemetry["turns"] += 1.0
            response_prompt_text, followup_carryover_applied = (
                runtime._with_followup_carryover(
                    text,
                    now_ts=turn_started_at,
                )
            )
            response_prompt_text = runtime._with_voice_profile_guidance(response_prompt_text)
            await runtime._respond_and_speak(response_prompt_text)
            response_success = bool(
                runtime._response_started and not runtime._barge_in.is_set()
            )
            llm_first_sentence_ms = (
                (runtime._first_sentence_at - runtime._response_start_at) * 1000.0
                if runtime._first_sentence_at is not None
                and runtime._response_start_at is not None
                else 0.0
            )
            tts_first_audio_ms = (
                (runtime._first_audio_at - runtime._response_start_at) * 1000.0
                if runtime._first_audio_at is not None
                and runtime._response_start_at is not None
                else 0.0
            )
            turn_tool_summaries = runtime._turn_tool_summaries_since(turn_started_at)
            if intent_class in {"answer", "hybrid"}:
                runtime._telemetry["intent_answer_total"] += 1.0
                if response_success:
                    runtime._telemetry["intent_answer_success"] += 1.0
            completion_outcome: bool | None = None
            if intent_class in {"action", "hybrid"}:
                completion_outcome = runtime._completion_success_from_summaries(
                    turn_tool_summaries
                )
                if completion_outcome is not None:
                    runtime._telemetry["intent_completion_total"] += 1.0
                    if completion_outcome:
                        runtime._telemetry["intent_completion_success"] += 1.0
            if intent_class in {"action", "hybrid"}:
                resolved: bool | None = completion_outcome is True
            else:
                resolved = True
            runtime._update_followup_carryover(
                text,
                intent_class,
                resolved=resolved,
                now_ts=turn_started_at,
            )
            runtime._record_conversation_trace(
                user_text=text,
                intent_class=intent_class,
                turn_started_at=turn_started_at,
                stt_latency_ms=stt_latency_ms,
                llm_first_sentence_ms=llm_first_sentence_ms,
                tts_first_audio_ms=tts_first_audio_ms,
                response_success=response_success,
                    tool_summaries=turn_tool_summaries,
                    lifecycle="completed",
                    used_brain_response=True,
                    followup_carryover_applied=followup_carryover_applied,
                    preference_updates=learned_preferences,
                )
            if int(runtime._telemetry["turns"]) % TELEMETRY_LOG_EVERY_TURNS == 0:
                runtime._refresh_tool_error_counters()
                snapshot = runtime._telemetry_snapshot()
                attention_source = runtime.presence.attention_source()
                log.info(
                    "Telemetry turns=%d barge_ins=%d stt=%.0fms llm=%.0fms tts=%.0fms service_errors=%d storage_errors=%d fallbacks=%d attention=%s",
                    int(snapshot["turns"]),
                    int(snapshot["barge_ins"]),
                    snapshot["avg_stt_latency_ms"],
                    snapshot["avg_llm_first_sentence_ms"],
                    snapshot["avg_tts_first_audio_ms"],
                    int(snapshot["service_errors"]),
                    int(snapshot["storage_errors"]),
                    int(snapshot["fallback_responses"]),
                    attention_source,
                )
            runtime._publish_observability_snapshot()

    except asyncio.CancelledError:
        pass
    finally:
        await runtime._stop_operator_server()
        if runtime._listen_task is not None:
            runtime._listen_task.cancel()
            with suppress(asyncio.CancelledError):
                await runtime._listen_task
            runtime._listen_task = None
        if getattr(runtime, "_watchdog_task", None) is not None:
            runtime._watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await runtime._watchdog_task
            runtime._watchdog_task = None
        if runtime._tts_task is not None:
            runtime._tts_task.cancel()
            with suppress(asyncio.CancelledError):
                await runtime._tts_task
            runtime._tts_task = None
        if runtime._filler_task is not None:
            runtime._filler_task.cancel()
            with suppress(asyncio.CancelledError):
                await runtime._filler_task
            runtime._filler_task = None
        with suppress(Exception):
            await runtime.brain.close()
        runtime.stop()


async def listen_loop(
    runtime: Any,
    *,
    require_sounddevice_fn: Callable[[str], None],
    sd_module: Any,
    to_mono_fn: Callable[[np.ndarray], np.ndarray],
    resample_audio_fn: Callable[[np.ndarray, int, int], np.ndarray],
    chunk_samples: int,
    min_utterance: float,
) -> None:
    """Continuously segment microphone audio into utterances."""

    chunks: list[np.ndarray] = []
    silence_start: float | None = None
    recording = False

    async def process_chunk(chunk_16k: np.ndarray) -> None:
        nonlocal chunks, silence_start, recording

        conf = runtime.vad.confidence(chunk_16k)
        runtime.presence.signals.vad_energy = max(0.0, min(1.0, conf))
        doa_angle, doa_speech = runtime.robot.get_doa()
        now = time.monotonic()
        runtime._last_doa_speech = doa_speech
        runtime._voice_controller().update_room_from_doa(doa_angle)
        if doa_angle is not None:
            if doa_speech is None or doa_speech:
                if runtime._last_doa_angle is None or abs(doa_angle - runtime._last_doa_angle) >= runtime.config.doa_change_threshold:
                    runtime._last_doa_angle = doa_angle
                    runtime._last_doa_update = now
                    runtime.presence.signals.doa_angle = doa_angle
                    runtime.presence.signals.doa_last_seen = now
            elif runtime._last_doa_update and (now - runtime._last_doa_update) > runtime.config.doa_timeout:
                runtime.presence.signals.doa_angle = None
                runtime._last_doa_angle = None
        elif runtime._last_doa_update and (now - runtime._last_doa_update) > runtime.config.doa_timeout:
            runtime.presence.signals.doa_angle = None
            runtime._last_doa_angle = None

        with runtime._lock:
            assistant_busy = runtime._speaking

        is_speech = runtime._compute_turn_taking(
            conf=conf,
            doa_speech=doa_speech,
            assistant_busy=assistant_busy,
            now=now,
        )

        if is_speech:
            if not recording:
                recording = True
                runtime.presence.signals.state = State.LISTENING
                log.debug("Speech detected")
            silence_start = None
            chunks.append(chunk_16k)

            if assistant_busy and not runtime._barge_in.is_set():
                runtime._barge_in.set()
                runtime._flush_output()
                runtime._clear_tts_queue()
                runtime.presence.signals.state = State.LISTENING
                runtime._telemetry["barge_ins"] += 1.0
                log.info("Barge-in detected")

        elif recording:
            chunks.append(chunk_16k)
            if silence_start is None:
                silence_start = time.monotonic()
            elif time.monotonic() - silence_start > runtime._voice_controller().silence_timeout():
                audio = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)

                runtime.vad.reset()
                runtime.presence.signals.vad_energy = 0.0
                chunks = []
                silence_start = None
                recording = False

                if audio.size == 0:
                    return

                duration = len(audio) / runtime.config.sample_rate
                if duration >= min_utterance:
                    await runtime._enqueue_utterance(audio)

        runtime._publish_voice_status()

    if not runtime._use_robot_audio:
        require_sounddevice_fn("local microphone capture")
        with sd_module.InputStream(
            samplerate=runtime.config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_samples,
        ) as stream:
            while True:
                data, overflowed = await asyncio.to_thread(stream.read, chunk_samples)
                if overflowed:
                    log.warning("Audio input buffer overflowed")
                await process_chunk(data[:, 0])
                await asyncio.sleep(0)

    else:
        pending_chunks: deque[np.ndarray] = deque()
        pending_len = 0
        while True:
            raw = runtime.robot.get_audio_sample()
            if raw is None:
                await asyncio.sleep(0.005)
                continue

            mono = to_mono_fn(raw)
            mono_16k = resample_audio_fn(mono, runtime._robot_input_sr, runtime.config.sample_rate)
            if mono_16k.size == 0:
                await asyncio.sleep(0)
                continue

            pending_chunks.append(mono_16k)
            pending_len += int(mono_16k.size)

            while pending_len >= chunk_samples:
                needed = chunk_samples
                parts: list[np.ndarray] = []
                while needed > 0 and pending_chunks:
                    head = pending_chunks[0]
                    if head.size <= needed:
                        parts.append(head)
                        pending_chunks.popleft()
                        needed -= int(head.size)
                    else:
                        parts.append(head[:needed])
                        pending_chunks[0] = head[needed:]
                        needed = 0
                if not parts:
                    break
                chunk = parts[0] if len(parts) == 1 else np.concatenate(parts)
                pending_len -= chunk_samples
                await process_chunk(chunk)

            await asyncio.sleep(0)


async def respond_and_speak(runtime: Any, text: str) -> None:
    """Get response and stream TTS with barge-in support."""
    runtime._barge_in.clear()
    runtime._clear_tts_queue()
    runtime._response_id += 1
    runtime._active_response_id = runtime._response_id
    runtime._response_started = False
    runtime._first_sentence_at = None
    runtime._first_audio_at = None
    runtime._response_start_at = time.monotonic()
    runtime._tts_gain = 1.0

    if runtime._filler_task is not None:
        runtime._filler_task.cancel()
    if runtime.tts is not None:
        runtime._filler_task = asyncio.create_task(
            runtime._thinking_filler(),
            name="thinking-filler",
        )

    with runtime._lock:
        runtime._speaking = True

    response_iter = runtime.brain.respond(text)

    try:
        async for sentence in response_iter:
            if runtime._barge_in.is_set():
                log.info("Barge-in — stopping response")
                runtime._flush_output()
                runtime._clear_tts_queue()
                runtime.robot.stop_sequence()
                break

            if not runtime._response_started:
                runtime._response_started = True
                runtime._first_sentence_at = time.monotonic()
                if runtime._response_start_at is not None:
                    latency_ms = (
                        (runtime._first_sentence_at - runtime._response_start_at) * 1000.0
                    )
                    runtime._telemetry["llm_first_sentence_total_ms"] += latency_ms
                    runtime._telemetry["llm_first_sentence_count"] += 1.0
                    log.info("LLM first sentence latency: %.0fms", latency_ms)
                if runtime._filler_task is not None:
                    runtime._filler_task.cancel()

            if runtime.tts:
                pause = runtime._confidence_pause(sentence)
                await runtime._tts_queue.put(
                    (runtime._active_response_id, sentence, False, pause)
                )
            else:
                print(f"  JARVIS: {sentence}")

    finally:
        with suppress(Exception):
            await response_iter.aclose()
        with runtime._lock:
            runtime._speaking = False
        if not runtime._barge_in.is_set():
            runtime.presence.signals.state = State.IDLE
            runtime._voice_controller().continue_listening()
        if runtime._filler_task is not None:
            runtime._filler_task.cancel()
        runtime._publish_voice_status()
