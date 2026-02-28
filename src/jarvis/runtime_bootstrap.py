"""Runtime bootstrap helpers for Jarvis initialization."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from typing import Any

import numpy as np

from jarvis.config import Config
from jarvis.observability import ObservabilityStore
from jarvis.skills import SkillRegistry
from jarvis.voice_attention import VoiceAttentionConfig, VoiceAttentionController


def apply_cli_overrides(config: Config, args: Any) -> None:
    if getattr(args, "no_motion", False):
        config.motion_enabled = False
    if getattr(args, "no_home", False):
        config.home_enabled = False
    if getattr(args, "no_hands", False):
        config.hand_track_enabled = False


def build_voice_attention_controller(config: Config) -> VoiceAttentionController:
    return VoiceAttentionController(
        VoiceAttentionConfig(
            wake_words=list(config.wake_words),
            mode=config.wake_mode,
            wake_calibration_profile=config.wake_calibration_profile,
            wake_word_sensitivity=config.wake_word_sensitivity,
            followup_window_sec=config.voice_followup_window_sec,
            timeout_profile=config.voice_timeout_profile,
            timeout_short_sec=config.voice_timeout_short_sec,
            timeout_normal_sec=config.voice_timeout_normal_sec,
            timeout_long_sec=config.voice_timeout_long_sec,
            barge_threshold_always_listening=config.barge_threshold_always_listening,
            barge_threshold_wake_word=config.barge_threshold_wake_word,
            barge_threshold_push_to_talk=config.barge_threshold_push_to_talk,
            min_post_wake_chars=config.voice_min_post_wake_chars,
            room_default=config.voice_room_default,
        )
    )


def build_skill_registry(config: Config) -> SkillRegistry:
    skills = SkillRegistry(
        skills_dir=config.skills_dir,
        allowlist=config.skills_allowlist,
        require_signature=config.skills_require_signature,
        signature_key=config.skills_signature_key,
        enabled=config.skills_enabled,
        state_path=config.skills_state_path,
    )
    skills.discover()
    return skills


def build_observability_store(config: Config) -> ObservabilityStore | None:
    if not config.observability_enabled:
        return None
    return ObservabilityStore(
        db_path=config.observability_db_path,
        state_path=config.observability_state_path,
        event_log_path=config.observability_event_log_path,
        failure_burst_threshold=config.observability_failure_burst_threshold,
    )


def telemetry_defaults() -> dict[str, float]:
    return {
        "turns": 0.0,
        "barge_ins": 0.0,
        "stt_latency_total_ms": 0.0,
        "stt_latency_count": 0.0,
        "llm_first_sentence_total_ms": 0.0,
        "llm_first_sentence_count": 0.0,
        "tts_first_audio_total_ms": 0.0,
        "tts_first_audio_count": 0.0,
        "service_errors": 0.0,
        "storage_errors": 0.0,
        "unknown_summary_details": 0.0,
        "fallback_responses": 0.0,
        "intent_turns_total": 0.0,
        "intent_answer_turns": 0.0,
        "intent_action_turns": 0.0,
        "intent_hybrid_turns": 0.0,
        "intent_answer_total": 0.0,
        "intent_answer_success": 0.0,
        "intent_completion_total": 0.0,
        "intent_completion_success": 0.0,
        "intent_corrections": 0.0,
        "preference_update_turns": 0.0,
        "preference_update_fields": 0.0,
        "multimodal_turns": 0.0,
        "multimodal_confidence_total": 0.0,
        "multimodal_low_confidence_turns": 0.0,
        "interruption_routes_total": 0.0,
        "interruption_resumes": 0.0,
        "interruption_replaces": 0.0,
        "interruption_clarifies": 0.0,
        "interruption_route_fallbacks": 0.0,
        "semantic_turn_decisions_total": 0.0,
        "semantic_turn_waits": 0.0,
        "semantic_turn_commits": 0.0,
        "semantic_turn_fallbacks": 0.0,
    }


def initialize_runtime_fields(
    runtime: Any,
    *,
    state_idle_value: str,
    conversation_trace_maxlen: int,
    episodic_timeline_maxlen: int,
    runtime_invariant_history_maxlen: int,
) -> None:
    runtime._last_doa_angle = None
    runtime._last_doa_update = 0.0
    runtime._last_doa_speech = None
    runtime._awaiting_confirmation = False
    runtime._pending_text = None
    runtime._awaiting_repair_confirmation = False
    runtime._repair_candidate_text = None
    runtime._followup_carryover = {
        "text": "",
        "intent": "",
        "timestamp": 0.0,
        "unresolved": False,
    }
    runtime._turn_choreography = {
        "phase": state_idle_value,
        "label": "idle_reset",
        "turn_lean": 0.0,
        "turn_tilt": 0.0,
        "turn_glance_yaw": 0.0,
        "updated_at": time.time(),
    }

    runtime._tts_queue = asyncio.Queue()
    runtime._tts_task = None
    runtime._watchdog_task = None
    runtime._response_id = 0
    runtime._active_response_id = 0
    runtime._response_started = False
    runtime._first_sentence_at = None
    runtime._first_audio_at = None
    runtime._response_start_at = None
    runtime._filler_task = None
    runtime._tts_gain = 1.0
    runtime._last_response_spoken_text = ""

    runtime._utterance_queue = asyncio.Queue(maxsize=1)
    runtime._listen_task = None
    runtime._operator_server = None
    runtime._output_stream = None
    runtime._started = False

    runtime._telemetry = telemetry_defaults()
    runtime._telemetry_error_counts = {}
    runtime._conversation_traces = deque(maxlen=conversation_trace_maxlen)
    runtime._turn_trace_seq = 0
    runtime._last_trace_turn_id = 0
    runtime._conversation_id = str(uuid.uuid4())
    runtime._interrupted_turn = None
    runtime._last_interruption_route = {}
    runtime._last_semantic_turn_route = {}
    runtime._episodic_timeline = deque(maxlen=episodic_timeline_maxlen)
    runtime._episode_seq = 0
    runtime._voice_user_profiles = {}
    runtime._last_learned_preferences = {}
    runtime._active_control_preset = "custom"
    runtime._personality_preview_snapshot = None
    runtime._stt_diagnostics = runtime._default_stt_diagnostics()
    runtime._runtime_invariant_checked_at = 0.0
    runtime._runtime_invariant_checked_monotonic = 0.0
    runtime._runtime_invariant_violations_total = 0
    runtime._runtime_invariant_auto_heals_total = 0
    runtime._runtime_invariant_recent = deque(maxlen=runtime_invariant_history_maxlen)


def reset_runtime_queues(runtime: Any) -> None:
    runtime._tts_queue = asyncio.Queue()
    runtime._utterance_queue = asyncio.Queue(maxsize=1)


def ensure_audio_sample_dtype(audio: np.ndarray) -> np.ndarray:
    if audio.dtype == np.float32:
        return audio
    return audio.astype(np.float32, copy=False)
