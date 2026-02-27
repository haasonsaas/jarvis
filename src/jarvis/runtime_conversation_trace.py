"""Conversation trace and episodic snapshot runtime helpers."""

from __future__ import annotations

import time
from collections import deque
from contextlib import suppress
from typing import Any


def record_conversation_trace(
    runtime: Any,
    *,
    user_text: str,
    intent_class: str,
    turn_started_at: float,
    stt_latency_ms: float | None,
    llm_first_sentence_ms: float | None,
    tts_first_audio_ms: float | None,
    response_success: bool | None,
    tool_summaries: list[dict[str, Any]],
    lifecycle: str,
    used_brain_response: bool,
    followup_carryover_applied: bool = False,
    preference_updates: dict[str, str] | None = None,
    multimodal_grounding: dict[str, Any] | None = None,
    episodic_timeline_maxlen: int,
) -> None:
    runtime._turn_trace_seq += 1
    now = time.time()
    total_ms = max(0.0, (now - turn_started_at) * 1000.0)
    stt_ms = max(0.0, float(stt_latency_ms or 0.0))
    llm_ms = max(0.0, float(llm_first_sentence_ms or 0.0))
    tts_ms = max(0.0, float(tts_first_audio_ms or 0.0))
    tool_calls = runtime._tool_call_trace_items(tool_summaries)
    completion_success = runtime._completion_success_from_summaries(tool_summaries)
    policy_decisions = runtime._policy_decisions_from_summaries(tool_summaries)
    if response_success is None:
        speak_status = "skipped"
    elif response_success:
        speak_status = "ok"
    else:
        speak_status = "interrupted"
    if completion_success is True:
        act_status = "ok"
    elif completion_success is False:
        act_status = "failed"
    else:
        act_status = "none"
    trace_item = {
        "turn_id": int(runtime._turn_trace_seq),
        "timestamp": now,
        "lifecycle": str(lifecycle),
        "intent": str(intent_class),
        "transcript": str(user_text).strip()[:400],
        "followup_carryover_applied": bool(followup_carryover_applied),
        "preference_updates": (
            {str(key): str(value) for key, value in preference_updates.items()}
            if isinstance(preference_updates, dict)
            else {}
        ),
        "multimodal_grounding": (
            {str(key): value for key, value in multimodal_grounding.items()}
            if isinstance(multimodal_grounding, dict)
            else {}
        ),
        "latencies_ms": {
            "stt": stt_ms,
            "llm_first_sentence": llm_ms,
            "tts_first_audio": tts_ms,
            "total": total_ms,
        },
        "turn_flow": [
            {"phase": "listen", "status": "ok", "latency_ms": stt_ms},
            {
                "phase": "think",
                "status": "ok" if used_brain_response else "skipped",
                "latency_ms": llm_ms,
            },
            {"phase": "speak", "status": speak_status, "latency_ms": tts_ms},
            {"phase": "act", "status": act_status, "tool_count": len(tool_calls)},
        ],
        "tool_calls": tool_calls,
        "policy_decisions": policy_decisions,
        "completion_success": completion_success,
        "response_success": response_success,
        "wake_mode": str(getattr(runtime._voice_controller(), "mode", "unknown")),
        "requester_user": runtime._active_voice_user(),
        "attention_source": runtime.presence.attention_source(),
        "turn_choreography": runtime._turn_choreography_snapshot(),
    }
    runtime._conversation_traces.appendleft(trace_item)
    record_episodic_snapshot(
        runtime,
        trace_item,
        episodic_timeline_maxlen=episodic_timeline_maxlen,
    )
    observability = getattr(runtime, "_observability", None)
    if observability is not None:
        with suppress(Exception):
            observability.record_event(
                "conversation_trace",
                {
                    "turn_id": int(runtime._turn_trace_seq),
                    "lifecycle": str(lifecycle),
                    "intent": str(intent_class),
                    "tool_count": len(tool_calls),
                    "policy_decision_count": len(policy_decisions),
                },
            )


def record_episodic_snapshot(
    runtime: Any,
    trace_item: dict[str, Any],
    *,
    episodic_timeline_maxlen: int,
) -> None:
    if not isinstance(trace_item, dict):
        return
    transcript = str(trace_item.get("transcript", "")).strip()
    if not transcript:
        return
    intent = str(trace_item.get("intent", "unknown")).strip().lower()
    lifecycle = str(trace_item.get("lifecycle", "unknown")).strip().lower()
    tool_calls = trace_item.get("tool_calls")
    tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0
    policy_decisions = trace_item.get("policy_decisions")
    policy_count = len(policy_decisions) if isinstance(policy_decisions, list) else 0
    completion_success = trace_item.get("completion_success")
    response_success = trace_item.get("response_success")

    important_lifecycle = {
        "memory_correction",
        "confirmation_requested",
        "repair_requested",
    }
    if intent not in {"action", "hybrid"} and tool_count == 0 and policy_count == 0 and lifecycle not in important_lifecycle:
        return
    if lifecycle == "completed" and intent == "answer" and tool_count == 0 and response_success is True:
        return

    tool_names: list[str] = []
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name", "")).strip()
            if name:
                tool_names.append(name)
    summary = transcript[:180]
    if tool_names:
        summary = f"{summary} -> tools: {', '.join(tool_names[:3])}"

    runtime._episode_seq = int(getattr(runtime, "_episode_seq", 0)) + 1
    snapshot = {
        "episode_id": int(runtime._episode_seq),
        "timestamp": float(trace_item.get("timestamp", time.time()) or time.time()),
        "turn_id": int(trace_item.get("turn_id", 0) or 0),
        "intent": intent,
        "lifecycle": lifecycle,
        "summary": summary,
        "tool_count": int(tool_count),
        "completion_success": completion_success,
        "response_success": response_success,
    }
    timeline = getattr(runtime, "_episodic_timeline", None)
    if not isinstance(timeline, deque):
        timeline = deque(maxlen=episodic_timeline_maxlen)
        runtime._episodic_timeline = timeline
    timeline.appendleft(snapshot)


def operator_episodic_timeline_provider(runtime: Any, limit: int = 20) -> list[dict[str, Any]]:
    size = max(1, min(200, int(limit)))
    timeline = getattr(runtime, "_episodic_timeline", None)
    if not isinstance(timeline, deque):
        return []
    return list(timeline)[:size]


def operator_conversation_trace_provider(runtime: Any, limit: int = 20) -> list[dict[str, Any]]:
    size = max(1, min(200, int(limit)))
    return list(runtime._conversation_traces)[:size]
