"""Conversation loop helpers extracted from Jarvis main runtime."""

from __future__ import annotations

import asyncio
import logging
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


def _safe_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _interruption_continuity_prompt(
    interrupted_turn: dict[str, Any],
    interruption_text: str,
    *,
    clarify: bool,
) -> str:
    previous_request = str(interrupted_turn.get("user_text", "")).strip()[:280]
    partial_response = str(interrupted_turn.get("spoken_text", "")).strip()[:420]
    interrupted_turn_id = _safe_positive_int(interrupted_turn.get("interrupted_turn_id"))
    continuity_lines = [
        f"Interrupted turn id: {interrupted_turn_id or 0}",
        f"Previous user request: {previous_request}",
        f"Assistant partial response: {partial_response}",
    ]
    if clarify:
        continuity_lines.append(
            "Instruction: Ask one concise clarifying question whether to continue the previous answer or switch tasks."
        )
    else:
        continuity_lines.append(
            "Instruction: Continue the interrupted answer from where it left off while incorporating the interruption transcript if relevant."
        )
    return (
        f"{interruption_text.strip()}\n\n"
        f"Interruption continuity context:\n{chr(10).join(continuity_lines)}"
    )


def _increment_telemetry(runtime: Any, key: str, amount: float = 1.0) -> None:
    telemetry = getattr(runtime, "_telemetry", None)
    if not isinstance(telemetry, dict):
        return
    current = telemetry.get(key, 0.0)
    try:
        base = float(current)
    except (TypeError, ValueError):
        base = 0.0
    telemetry[key] = base + float(amount)


def _record_llm_usage_metrics(runtime: Any) -> None:
    brain = getattr(runtime, "brain", None)
    if brain is None or not hasattr(brain, "latest_llm_usage"):
        return
    try:
        usage = brain.latest_llm_usage()
    except Exception:
        return
    if not isinstance(usage, dict):
        return
    try:
        total_tokens = int(usage.get("total_tokens", 0) or 0)
    except (TypeError, ValueError):
        total_tokens = 0
    if total_tokens <= 0:
        return
    try:
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    except (TypeError, ValueError):
        prompt_tokens = 0
    try:
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        completion_tokens = 0
    try:
        cost_usd = float(usage.get("cost_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        cost_usd = 0.0
    _increment_telemetry(runtime, "llm_prompt_tokens_total", float(max(0, prompt_tokens)))
    _increment_telemetry(runtime, "llm_completion_tokens_total", float(max(0, completion_tokens)))
    _increment_telemetry(runtime, "llm_total_tokens_total", float(max(0, total_tokens)))
    _increment_telemetry(runtime, "llm_cost_usd_total", max(0.0, cost_usd))
    _increment_telemetry(runtime, "llm_usage_samples", 1.0)


def _default_turn_understanding_payload() -> dict[str, Any]:
    return {
        "intent_class": "answer",
        "looks_like_correction": False,
        "apply_followup_carryover": False,
        "confirmation_intent": "none",
        "memory_command": "none",
        "memory_id": None,
        "memory_text": "",
        "route_confidence": 0.0,
        "uncertainty_reason": "turn_understanding_unavailable",
        "route_source": "fallback",
        "fallback_reason": "router_unavailable",
        "guardrail_correction": "none",
    }


async def _understand_turn(
    runtime: Any,
    text: str,
    *,
    awaiting_confirmation: bool,
    awaiting_repair_confirmation: bool,
) -> dict[str, Any]:
    payload = _default_turn_understanding_payload()
    brain = getattr(runtime, "brain", None)
    if brain is None or not hasattr(brain, "understand_turn"):
        return payload
    context = getattr(runtime, "_followup_carryover", {})
    try:
        decision = await brain.understand_turn(
            user_text=text,
            followup_context=context if isinstance(context, dict) else {},
            awaiting_confirmation=awaiting_confirmation,
            awaiting_repair_confirmation=awaiting_repair_confirmation,
        )
        if hasattr(brain, "latest_turn_understanding_trace"):
            trace_payload = brain.latest_turn_understanding_trace()
            if isinstance(trace_payload, dict) and trace_payload:
                return {str(key): value for key, value in trace_payload.items()}
        if hasattr(decision, "model_dump") and callable(decision.model_dump):
            model_payload = decision.model_dump()
            if isinstance(model_payload, dict):
                payload.update({str(key): value for key, value in model_payload.items()})
                return payload
    except Exception as exc:
        log.warning("Turn-understanding routing failed; using fallback: %s", exc)
        payload["fallback_reason"] = "router_error"
    return payload


async def _semantic_turn_should_commit(
    runtime: Any,
    *,
    audio: np.ndarray,
    assistant_busy: bool,
    silence_elapsed_sec: float,
    utterance_duration_sec: float,
) -> bool:
    if assistant_busy:
        return True
    config = getattr(runtime, "config", None)
    if not bool(getattr(config, "semantic_turn_enabled", False)):
        return True
    brain = getattr(runtime, "brain", None)
    if brain is None or not hasattr(brain, "semantic_turn_decision"):
        return True
    transcribe_fn = getattr(runtime, "_transcribe_with_fallback", None)
    if not callable(transcribe_fn):
        return True

    loop = asyncio.get_event_loop()
    try:
        transcript = await loop.run_in_executor(None, transcribe_fn, audio)
    except Exception as exc:
        log.warning("Semantic turn pre-transcription failed; committing utterance: %s", exc)
        _increment_telemetry(runtime, "semantic_turn_decisions_total", 1.0)
        _increment_telemetry(runtime, "semantic_turn_commits", 1.0)
        _increment_telemetry(runtime, "semantic_turn_fallbacks", 1.0)
        runtime._last_semantic_turn_route = {
            "action": "commit",
            "route_confidence": 0.0,
            "route_source": "fallback",
            "fallback_reason": "pretranscribe_error",
            "guardrail_correction": "none",
        }
        return True

    text = str(transcript or "").strip()
    if not text:
        _increment_telemetry(runtime, "semantic_turn_decisions_total", 1.0)
        _increment_telemetry(runtime, "semantic_turn_commits", 1.0)
        runtime._last_semantic_turn_route = {
            "action": "commit",
            "route_confidence": 0.0,
            "route_source": "fallback",
            "fallback_reason": "empty_transcript",
            "guardrail_correction": "none",
        }
        return True

    max_chars = int(getattr(config, "semantic_turn_max_transcript_chars", 220) or 220)
    if max_chars > 0:
        text = text[:max_chars]

    route_payload: dict[str, Any] = {
        "action": "commit",
        "route_confidence": 0.0,
        "route_source": "fallback",
        "fallback_reason": "router_unavailable",
        "guardrail_correction": "none",
    }
    try:
        decision = await brain.semantic_turn_decision(
            transcript=text,
            silence_elapsed_sec=silence_elapsed_sec,
            utterance_duration_sec=utterance_duration_sec,
        )
        if hasattr(brain, "latest_semantic_turn_trace"):
            trace_payload = brain.latest_semantic_turn_trace()
            if isinstance(trace_payload, dict) and trace_payload:
                route_payload = {str(key): value for key, value in trace_payload.items()}
        if (
            not route_payload
            and hasattr(decision, "model_dump")
            and callable(decision.model_dump)
        ):
            route_payload = {str(key): value for key, value in decision.model_dump().items()}
    except Exception as exc:
        log.warning("Semantic turn routing failed; committing utterance: %s", exc)
        route_payload = {
            "action": "commit",
            "route_confidence": 0.0,
            "route_source": "fallback",
            "fallback_reason": "router_error",
            "guardrail_correction": "none",
        }

    action = str(route_payload.get("action", "commit")).strip().lower() or "commit"
    if action not in {"commit", "wait"}:
        action = "commit"
    route_payload["action"] = action
    route_payload["transcript_preview"] = text[:120]
    runtime._last_semantic_turn_route = dict(route_payload)

    _increment_telemetry(runtime, "semantic_turn_decisions_total", 1.0)
    if str(route_payload.get("route_source", "")).strip().lower() == "fallback":
        _increment_telemetry(runtime, "semantic_turn_fallbacks", 1.0)
    if action == "wait":
        _increment_telemetry(runtime, "semantic_turn_waits", 1.0)
        return False
    _increment_telemetry(runtime, "semantic_turn_commits", 1.0)
    return True


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
                understanding = await _understand_turn(
                    runtime,
                    text,
                    awaiting_confirmation=True,
                    awaiting_repair_confirmation=False,
                )
                intent = str(understanding.get("confirmation_intent", "none")).strip().lower()
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
                understanding = await _understand_turn(
                    runtime,
                    text,
                    awaiting_confirmation=False,
                    awaiting_repair_confirmation=True,
                )
                intent = str(understanding.get("confirmation_intent", "none")).strip().lower()
                if intent == "confirm" and runtime._repair_candidate_text:
                    text = runtime._repair_candidate_text
                    runtime._awaiting_repair_confirmation = False
                    runtime._repair_candidate_text = None
                    repair_resolved_this_turn = True
                elif intent in {"deny", "repeat"}:
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

            user_text = text
            response_input_text = user_text
            interruption_route: dict[str, Any] = {}
            continuation_from_turn_id: int | None = None
            interrupted_turn = getattr(runtime, "_interrupted_turn", None)
            if isinstance(interrupted_turn, dict):
                interruption_route = {
                    "strategy": "replace",
                    "route_confidence": 0.0,
                    "route_source": "fallback",
                    "fallback_reason": "router_unavailable",
                    "guardrail_correction": "none",
                    "user_intent": "unknown",
                    "uncertainty_reason": "interruption_router_unavailable",
                }
                if hasattr(runtime.brain, "route_interruption"):
                    try:
                        route = await runtime.brain.route_interruption(
                            interruption_text=user_text,
                            interrupted_user_text=str(interrupted_turn.get("user_text", "")),
                            interrupted_spoken_text=str(interrupted_turn.get("spoken_text", "")),
                        )
                        if hasattr(runtime.brain, "latest_interruption_route_trace"):
                            trace_payload = runtime.brain.latest_interruption_route_trace()
                            if isinstance(trace_payload, dict) and trace_payload:
                                interruption_route = {
                                    str(key): value for key, value in trace_payload.items()
                                }
                        if (
                            not interruption_route
                            and hasattr(route, "model_dump")
                            and callable(route.model_dump)
                        ):
                            interruption_route = {
                                str(key): value for key, value in route.model_dump().items()
                            }
                    except Exception as exc:
                        log.warning("Interruption routing failed; defaulting to replace: %s", exc)
                        interruption_route = {
                            "strategy": "replace",
                            "route_confidence": 0.0,
                            "route_source": "fallback",
                            "fallback_reason": "router_error",
                            "guardrail_correction": "none",
                            "user_intent": "unknown",
                            "uncertainty_reason": "interruption_router_error",
                        }

                strategy = str(interruption_route.get("strategy", "replace")).strip().lower() or "replace"
                if strategy not in {"replace", "resume", "clarify"}:
                    strategy = "replace"
                route_source = str(interruption_route.get("route_source", "")).strip().lower()
                _increment_telemetry(runtime, "interruption_routes_total", 1.0)
                if route_source == "fallback":
                    _increment_telemetry(runtime, "interruption_route_fallbacks", 1.0)

                interrupted_turn_id = _safe_positive_int(
                    interrupted_turn.get("interrupted_turn_id")
                )
                if interrupted_turn_id is not None:
                    continuation_from_turn_id = interrupted_turn_id

                if strategy == "resume":
                    _increment_telemetry(runtime, "interruption_resumes", 1.0)
                    response_input_text = _interruption_continuity_prompt(
                        interrupted_turn,
                        user_text,
                        clarify=False,
                    )
                elif strategy == "clarify":
                    _increment_telemetry(runtime, "interruption_clarifies", 1.0)
                    response_input_text = _interruption_continuity_prompt(
                        interrupted_turn,
                        user_text,
                        clarify=True,
                    )
                else:
                    _increment_telemetry(runtime, "interruption_replaces", 1.0)

                interruption_route["strategy"] = strategy
                interruption_route["interrupted_turn_id"] = interrupted_turn_id
                interruption_route["continuation_prompt_applied"] = bool(
                    strategy in {"resume", "clarify"}
                )
                runtime._last_interruption_route = dict(interruption_route)
                runtime._interrupted_turn = None

            turn_understanding = await _understand_turn(
                runtime,
                user_text,
                awaiting_confirmation=False,
                awaiting_repair_confirmation=False,
            )
            intent_class = str(turn_understanding.get("intent_class", "answer")).strip().lower()
            if intent_class not in {"answer", "action", "hybrid"}:
                intent_class = "answer"
            runtime._telemetry["intent_turns_total"] += 1.0
            if intent_class == "action":
                runtime._telemetry["intent_action_turns"] += 1.0
            elif intent_class == "hybrid":
                runtime._telemetry["intent_hybrid_turns"] += 1.0
            else:
                runtime._telemetry["intent_answer_turns"] += 1.0
            looks_like_correction = bool(
                turn_understanding.get("looks_like_correction", False)
            )
            if looks_like_correction:
                runtime._telemetry["intent_corrections"] += 1.0
            apply_followup_carryover = bool(
                turn_understanding.get("apply_followup_carryover", False)
            )
            memory_command = str(
                turn_understanding.get("memory_command", "none")
            ).strip().lower()
            memory_id = _safe_positive_int(turn_understanding.get("memory_id"))
            memory_text = str(turn_understanding.get("memory_text", "")).strip()

            turn_started_at = time.time()
            learned_preferences: dict[str, str] = {}
            if hasattr(runtime, "_learn_voice_preferences"):
                try:
                    learned_preferences = runtime._learn_voice_preferences(
                        user_text,
                        now_ts=turn_started_at,
                    )
                except Exception:
                    learned_preferences = {}
            multimodal_grounding: dict[str, Any] = {}
            if hasattr(runtime, "_multimodal_grounding_snapshot"):
                try:
                    multimodal_grounding = runtime._multimodal_grounding_snapshot()
                except Exception:
                    multimodal_grounding = {}
            if isinstance(multimodal_grounding, dict) and multimodal_grounding:
                runtime._telemetry["multimodal_turns"] += 1.0
                try:
                    confidence = float(
                        multimodal_grounding.get("overall_confidence", 0.0) or 0.0
                    )
                except (TypeError, ValueError):
                    confidence = 0.0
                if confidence < 0.0:
                    confidence = 0.0
                if confidence > 1.0:
                    confidence = 1.0
                runtime._telemetry["multimodal_confidence_total"] += confidence
                if (
                    str(multimodal_grounding.get("confidence_band", "")).strip().lower()
                    == "low"
                ):
                    runtime._telemetry["multimodal_low_confidence_turns"] += 1.0
            if (
                not repair_resolved_this_turn
                and runtime._requires_stt_repair(
                    user_text,
                    intent_class,
                    looks_like_correction=looks_like_correction,
                )
            ):
                runtime._awaiting_repair_confirmation = True
                runtime._repair_candidate_text = user_text
                prompt = runtime._repair_prompt(user_text)
                if runtime.tts:
                    await runtime._tts_queue.put(
                        (runtime._active_response_id, prompt, True, 0.0)
                    )
                else:
                    print(f"  JARVIS: {prompt}")
                runtime.presence.signals.state = State.LISTENING
                runtime._publish_voice_status()
                runtime._record_conversation_trace(
                    user_text=user_text,
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
                    multimodal_grounding=multimodal_grounding,
                    route_policy={},
                    correction_outcome="none",
                    interruption_route=interruption_route,
                    continuation_from_turn_id=continuation_from_turn_id,
                )
                continue

            memory_correction: tuple[str, dict[str, Any]] | None = None
            if memory_command == "memory_forget" and memory_id is not None:
                memory_correction = ("memory_forget", {"memory_id": memory_id})
            elif (
                memory_command == "memory_update"
                and memory_id is not None
                and memory_text
            ):
                memory_correction = (
                    "memory_update",
                    {"memory_id": memory_id, "text": memory_text},
                )
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
                    user_text,
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
                    user_text=user_text,
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
                    multimodal_grounding=multimodal_grounding,
                    route_policy={},
                    correction_outcome="applied" if correction_succeeded else "failed",
                    interruption_route=interruption_route,
                    continuation_from_turn_id=continuation_from_turn_id,
                )
                continue

            if runtime._requires_confirmation(time.monotonic()):
                runtime._awaiting_confirmation = True
                runtime._pending_text = user_text
                runtime._telemetry["fallback_responses"] += 1.0
                runtime._update_followup_carryover(
                    user_text,
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
                    user_text=user_text,
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
                    multimodal_grounding=multimodal_grounding,
                    route_policy={},
                    correction_outcome="none",
                    interruption_route=interruption_route,
                    continuation_from_turn_id=continuation_from_turn_id,
                )
                continue

            runtime._telemetry["turns"] += 1.0
            response_prompt_text, followup_carryover_applied = (
                runtime._with_followup_carryover(
                    user_text,
                    now_ts=turn_started_at,
                    apply=apply_followup_carryover,
                )
            )
            if response_input_text != user_text:
                response_prompt_text = response_input_text
                followup_carryover_applied = False
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
                user_text,
                intent_class,
                resolved=resolved,
                now_ts=turn_started_at,
            )

            if response_success:
                runtime._interrupted_turn = None
            elif bool(runtime._barge_in.is_set() and runtime._response_started):
                interruption_turn_id = _safe_positive_int(getattr(runtime, "_turn_trace_seq", 0))
                if interruption_turn_id is None:
                    interruption_turn_id = 0
                interruption_turn_id += 1
                runtime._interrupted_turn = {
                    "interrupted_turn_id": interruption_turn_id,
                    "user_text": str(user_text).strip()[:300],
                    "spoken_text": str(getattr(runtime, "_last_response_spoken_text", "")).strip()[:500],
                    "captured_at": time.time(),
                    "response_prompt_text": str(response_prompt_text).strip()[:500],
                }

            route_policy_payload = (
                runtime.brain.latest_policy_route_trace()
                if hasattr(runtime.brain, "latest_policy_route_trace")
                else {}
            )
            if isinstance(route_policy_payload, dict):
                if str(route_policy_payload.get("router_variant", "")).strip().lower() == "canary":
                    _increment_telemetry(runtime, "router_canary_turns_total", 1.0)
                shadow_agreement = route_policy_payload.get("shadow_agreement")
                if isinstance(shadow_agreement, bool):
                    _increment_telemetry(runtime, "router_shadow_comparisons_total", 1.0)
                    if shadow_agreement:
                        _increment_telemetry(runtime, "router_shadow_agreements_total", 1.0)
                    else:
                        _increment_telemetry(runtime, "router_shadow_disagreements_total", 1.0)

            runtime._record_conversation_trace(
                user_text=user_text,
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
                multimodal_grounding=multimodal_grounding,
                route_policy=route_policy_payload,
                correction_outcome=(
                    "resolved"
                    if looks_like_correction and resolved is True
                    else "unresolved"
                    if looks_like_correction and resolved is False
                    else "none"
                ),
                interruption_route=interruption_route,
                continuation_from_turn_id=continuation_from_turn_id,
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
            else:
                silence_elapsed_sec = time.monotonic() - silence_start
                if silence_elapsed_sec <= runtime._voice_controller().silence_timeout():
                    runtime._publish_voice_status()
                    return
                audio = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
                if audio.size == 0:
                    runtime.vad.reset()
                    runtime.presence.signals.vad_energy = 0.0
                    chunks = []
                    silence_start = None
                    recording = False
                    return

                duration = len(audio) / runtime.config.sample_rate
                should_commit = True
                if duration >= min_utterance:
                    should_commit = await _semantic_turn_should_commit(
                        runtime,
                        audio=audio,
                        assistant_busy=assistant_busy,
                        silence_elapsed_sec=float(silence_elapsed_sec),
                        utterance_duration_sec=float(duration),
                    )
                if duration >= min_utterance and not should_commit:
                    extension_sec = float(
                        getattr(runtime.config, "semantic_turn_extension_sec", 0.6) or 0.6
                    )
                    silence_start = time.monotonic()
                    runtime._voice_controller().continue_listening(
                        now=time.monotonic(),
                        window_sec=extension_sec,
                    )
                    runtime.presence.signals.state = State.LISTENING
                    runtime._publish_voice_status()
                    return

                runtime.vad.reset()
                runtime.presence.signals.vad_energy = 0.0
                chunks = []
                silence_start = None
                recording = False
                if duration >= min_utterance and should_commit:
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
    spoken_sentences: list[str] = []
    runtime._last_response_spoken_text = ""

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
            spoken_sentences.append(sentence.strip())

    finally:
        with suppress(Exception):
            await response_iter.aclose()
        _record_llm_usage_metrics(runtime)
        runtime._last_response_spoken_text = " ".join(
            sentence for sentence in spoken_sentences if sentence
        ).strip()
        with runtime._lock:
            runtime._speaking = False
        if not runtime._barge_in.is_set():
            runtime.presence.signals.state = State.IDLE
            runtime._voice_controller().continue_listening()
        if runtime._filler_task is not None:
            runtime._filler_task.cancel()
        runtime._publish_voice_status()
