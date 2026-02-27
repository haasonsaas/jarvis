"""Jarvis — main conversation loop.

Pipeline:
  1. Presence loop runs continuously (idle breathing, micro-behaviors)
  2. VAD detects speech → state = LISTENING → STT captures utterance
  3. On end-of-utterance → state = THINKING → Claude streams response
  4. TTS streams sentences as they arrive → state = SPEAKING
  5. Barge-in: VAD during playback → stop TTS, feed new utterance
  6. Back to idle

Face tracking runs in parallel, feeding into the presence loop signals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import logging
import re
import signal
import time
import threading
from pathlib import Path
from collections import deque
from contextlib import suppress
from typing import Any

import numpy as np

from jarvis.config import Config
from jarvis.backup_restore import create_backup_bundle, restore_backup_bundle
from jarvis.robot.controller import RobotController
from jarvis.presence import PresenceLoop, State
from jarvis.audio.vad import VoiceActivityDetector, CHUNK_SAMPLES
from jarvis.audio.stt import SpeechToText
from jarvis.audio.tts import TextToSpeech
from jarvis.brain import Brain
from jarvis.observability import ObservabilityStore
from jarvis.operator_server import OperatorServer
from jarvis.skills import SkillRegistry
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES
from jarvis.tools.robot import bind as bind_robot_tools
from jarvis.tools import services as service_tools
from jarvis.tools.services import (
    set_runtime_observability_state,
    set_runtime_skills_state,
    set_runtime_voice_state,
)
from jarvis.tool_summary import list_summaries
from jarvis.audio.runtime_audio import (
    require_sounddevice as _require_sounddevice_or_raise,
    to_mono as _audio_to_mono,
    resample_audio as _audio_resample,
)
from jarvis.runtime_operator_control import handle_operator_control as _runtime_handle_operator_control
from jarvis.runtime_operator_status import (
    normalize_operator_auth_mode as _runtime_normalize_operator_auth_mode,
    operator_auth_risk as _runtime_operator_auth_risk,
    operator_status_provider as _runtime_operator_status_provider,
)
from jarvis.runtime_observability_status import (
    default_observability_status_snapshot as _runtime_default_observability_status_snapshot,
)
from jarvis.runtime_conversation_trace import (
    operator_conversation_trace_provider as _runtime_operator_conversation_trace_provider,
    operator_episodic_timeline_provider as _runtime_operator_episodic_timeline_provider,
    record_conversation_trace as _runtime_record_conversation_trace,
    record_episodic_snapshot as _runtime_record_episodic_snapshot,
)
from jarvis.runtime_memory_correction import (
    parse_memory_correction_command as _runtime_parse_memory_correction_command,
)
from jarvis.runtime_turn import (
    classify_user_intent as _turn_classify_user_intent,
    completion_success_from_summaries as _turn_completion_success_from_summaries,
    is_followup_carryover_candidate as _turn_is_followup_carryover_candidate,
    looks_like_user_correction as _turn_looks_like_user_correction,
    policy_decisions_from_summaries as _turn_policy_decisions_from_summaries,
    tool_call_trace_items as _turn_tool_call_trace_items,
    turn_tool_summaries_since as _turn_tool_summaries_since,
    update_followup_carryover as _turn_update_followup_carryover,
    with_followup_carryover as _turn_with_followup_carryover,
)
from jarvis.runtime_telemetry import (
    confidence_pause as _runtime_confidence_pause,
    conversation_latency_analytics as _runtime_conversation_latency_analytics,
    default_stt_diagnostics as _runtime_default_stt_diagnostics,
    normalize_tts_chunk as _runtime_normalize_tts_chunk,
    percentile as _runtime_percentile,
    policy_decision_analytics as _runtime_policy_decision_analytics,
    stt_confidence_band as _runtime_stt_confidence_band,
    stt_diagnostics_snapshot as _runtime_stt_diagnostics_snapshot,
    summarize_tool_error_counters as _runtime_summarize_tool_error_counters,
    telemetry_snapshot as _runtime_telemetry_snapshot,
    transcribe_with_fallback as _runtime_transcribe_with_fallback,
    transcribe_with_optional_diagnostics as _runtime_transcribe_with_optional_diagnostics,
    update_stt_diagnostics as _runtime_update_stt_diagnostics,
)
from jarvis.runtime_state import (
    apply_control_preset as _runtime_apply_control_preset,
    apply_runtime_profile as _runtime_apply_runtime_profile,
    check_runtime_invariants as _runtime_check_runtime_invariants,
    load_runtime_state as _runtime_load_runtime_state,
    preset_profile as _runtime_preset_profile,
    runtime_invariant_snapshot as _runtime_runtime_invariant_snapshot,
    runtime_profile_snapshot as _runtime_runtime_profile_snapshot,
    save_runtime_state as _runtime_save_runtime_state,
)
from jarvis.runtime_startup import (
    operator_control_schema as _runtime_operator_control_schema,
    startup_blockers as _runtime_startup_blockers,
)
from jarvis.runtime_conversation import (
    listen_loop as _runtime_listen_loop,
    respond_and_speak as _runtime_respond_and_speak,
    run as _runtime_run,
)
from jarvis.runtime_voice_profile import (
    active_voice_profile as _runtime_active_voice_profile,
    active_voice_user as _runtime_active_voice_user,
    parse_control_bool as _runtime_parse_control_bool,
    parse_control_choice as _runtime_parse_control_choice,
    with_voice_profile_guidance as _runtime_with_voice_profile_guidance,
)
from jarvis.runtime_preferences import (
    detect_voice_profile_updates as _runtime_detect_voice_profile_updates,
    voice_profile_summary as _runtime_voice_profile_summary,
)
from jarvis.runtime_multimodal import (
    multimodal_grounding_snapshot as _runtime_multimodal_grounding_snapshot,
)
from jarvis.runtime_constants import (
    ATTENTION_RECENCY_SEC,
    CONVERSATION_TRACE_MAXLEN,
    EPISODIC_TIMELINE_MAXLEN,
    INTENDED_QUERY_MIN_ATTENTION,
    MIN_UTTERANCE,
    REPAIR_CONFIRMATION_TEMPLATE,
    REPAIR_CONFIDENCE_THRESHOLD,
    REPAIR_MIN_WORDS,
    RUNTIME_INVARIANT_HISTORY_MAXLEN,
    TELEMETRY_SERVICE_ERROR_DETAILS,
    TELEMETRY_STORAGE_ERROR_DETAILS,
    THINKING_FILLER_DELAY,
    THINKING_FILLER_TEXT,
    TTS_CONFIDENCE_PAUSE_SEC,
    TTS_GAIN_SMOOTH,
    TTS_LOW_CONFIDENCE_WORDS,
    TTS_SENTENCE_PAUSE_SEC,
    TTS_TARGET_RMS,
    TURN_CHOREOGRAPHY_CUES,
    TURN_TAKING_BARGE_IN_THRESHOLD,  # noqa: F401  # compatibility export for tests/importers
    TURN_TAKING_THRESHOLD,
    VALID_BACKCHANNEL_STYLES,
    VALID_CONTROL_PRESETS,
    VALID_OPERATOR_AUTH_MODES,
    VALID_PERSONA_STYLES,
    VALID_VOICE_PROFILE_CONFIRMATIONS,
    VALID_VOICE_PROFILE_PACE,
    VALID_VOICE_PROFILE_TONE,
    VALID_VOICE_PROFILE_VERBOSITY,
    WATCHDOG_POLL_SEC,
)
from jarvis.voice_attention import (
    VALID_TIMEOUT_PROFILES,
    VALID_WAKE_MODES,
    VoiceAttentionConfig,
    VoiceAttentionController,
)

_SOUNDDEVICE_IMPORT_ERROR: str | None = None
try:
    import sounddevice as sd
except Exception as e:  # pragma: no cover - exercised via runtime guard tests
    sd = None  # type: ignore[assignment]
    _SOUNDDEVICE_IMPORT_ERROR = str(e)

log = logging.getLogger(__name__)


def _require_sounddevice(feature: str) -> None:
    _require_sounddevice_or_raise(sd, _SOUNDDEVICE_IMPORT_ERROR, feature=feature)


_to_mono = _audio_to_mono
_resample_audio = _audio_resample


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Jarvis AI Assistant on Reachy Mini")
    p.add_argument("--sim", action="store_true", help="Simulation mode (no robot)")
    p.add_argument("--no-vision", action="store_true", help="Disable face tracking")
    p.add_argument("--no-motion", action="store_true", help="Disable robot motion")
    p.add_argument("--no-hands", action="store_true", help="Disable hand tracking")
    p.add_argument("--no-home", action="store_true", help="Disable smart home tools")
    p.add_argument("--no-tts", action="store_true", help="Print responses instead of speaking")
    p.add_argument("--debug", action="store_true", help="Verbose logging")
    maintenance = p.add_mutually_exclusive_group()
    maintenance.add_argument("--backup", metavar="PATH", help="Write a state backup bundle to PATH and exit.")
    maintenance.add_argument("--restore", metavar="PATH", help="Restore state from backup bundle PATH and exit.")
    p.add_argument("--force", action="store_true", help="With --restore, overwrite existing destination files.")
    return p.parse_args(argv)


class Jarvis:
    """Main application orchestrating all subsystems."""

    def __init__(self, args: argparse.Namespace):
        self.config = Config()
        self.args = args

        # Robot
        self.robot = RobotController(
            host=self.config.reachy_host,
            sim=args.sim,
            connection_mode=self.config.reachy_connection_mode,
            media_backend=self.config.reachy_media_backend,
            automatic_body_yaw=self.config.reachy_automatic_body_yaw,
        )

        # Presence loop (the soul)
        self.presence = PresenceLoop(self.robot)
        self.presence.set_backchannel_style(self.config.backchannel_style)
        if getattr(args, "no_motion", False):
            self.config.motion_enabled = False
        if getattr(args, "no_home", False):
            self.config.home_enabled = False
        if getattr(args, "no_hands", False):
            self.config.hand_track_enabled = False

        self._voice_attention = VoiceAttentionController(
            VoiceAttentionConfig(
                wake_words=list(self.config.wake_words),
                mode=self.config.wake_mode,
                wake_calibration_profile=self.config.wake_calibration_profile,
                wake_word_sensitivity=self.config.wake_word_sensitivity,
                followup_window_sec=self.config.voice_followup_window_sec,
                timeout_profile=self.config.voice_timeout_profile,
                timeout_short_sec=self.config.voice_timeout_short_sec,
                timeout_normal_sec=self.config.voice_timeout_normal_sec,
                timeout_long_sec=self.config.voice_timeout_long_sec,
                barge_threshold_always_listening=self.config.barge_threshold_always_listening,
                barge_threshold_wake_word=self.config.barge_threshold_wake_word,
                barge_threshold_push_to_talk=self.config.barge_threshold_push_to_talk,
                min_post_wake_chars=self.config.voice_min_post_wake_chars,
                room_default=self.config.voice_room_default,
            )
        )
        self._runtime_state_path = Path(self.config.runtime_state_path).expanduser()

        self._skills = SkillRegistry(
            skills_dir=self.config.skills_dir,
            allowlist=self.config.skills_allowlist,
            require_signature=self.config.skills_require_signature,
            signature_key=self.config.skills_signature_key,
            enabled=self.config.skills_enabled,
            state_path=self.config.skills_state_path,
        )
        self._skills.discover()
        service_tools.set_skill_registry(self._skills)
        set_runtime_skills_state(self._skills.status_snapshot())

        # Bind tools to robot + presence
        bind_robot_tools(self.robot, self.presence, self.config)

        # Audio
        self.vad = VoiceActivityDetector(
            threshold=self.config.vad_threshold,
            sample_rate=self.config.sample_rate,
        )
        self.stt = SpeechToText(model_size=self.config.whisper_model)
        self._stt_secondary: SpeechToText | None = None
        if self.config.stt_fallback_enabled:
            fallback_model = (self.config.whisper_model_fallback or "").strip()
            if fallback_model and fallback_model != self.config.whisper_model:
                self._stt_secondary = SpeechToText(model_size=fallback_model)
        self.tts = TextToSpeech(
            api_key=self.config.elevenlabs_api_key,
            voice_id=self.config.elevenlabs_voice_id,
            sample_rate=self.config.sample_rate,
        ) if not args.no_tts and self.config.elevenlabs_api_key else None
        self._tts_output_enabled = True

        # Brain
        self.brain = Brain(self.config, self.presence)

        self._observability: ObservabilityStore | None = None
        if self.config.observability_enabled:
            self._observability = ObservabilityStore(
                db_path=self.config.observability_db_path,
                state_path=self.config.observability_state_path,
                event_log_path=self.config.observability_event_log_path,
                failure_burst_threshold=self.config.observability_failure_burst_threshold,
            )
        self._last_observability_snapshot_at = 0.0

        # Face tracker (lazy init)
        self.face_tracker = None
        self.hand_tracker = None

        # Barge-in control — use a lock for thread safety
        self._lock = threading.Lock()
        self._speaking = False
        self._barge_in = threading.Event()

        self._use_robot_audio = False
        self._robot_input_sr = self.config.sample_rate
        self._robot_output_sr = self.config.sample_rate

        self._last_doa_angle: float | None = None
        self._last_doa_update: float = 0.0
        self._last_doa_speech: bool | None = None
        self._awaiting_confirmation = False
        self._pending_text: str | None = None
        self._awaiting_repair_confirmation = False
        self._repair_candidate_text: str | None = None
        self._followup_carryover: dict[str, Any] = {
            "text": "",
            "intent": "",
            "timestamp": 0.0,
            "unresolved": False,
        }
        self._turn_choreography: dict[str, Any] = {
            "phase": str(State.IDLE.value),
            "label": "idle_reset",
            "turn_lean": 0.0,
            "turn_tilt": 0.0,
            "turn_glance_yaw": 0.0,
            "updated_at": time.time(),
        }

        self._tts_queue: asyncio.Queue[tuple[int, str, bool, float]] = asyncio.Queue()
        self._tts_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._response_id = 0
        self._active_response_id = 0
        self._response_started = False
        self._first_sentence_at: float | None = None
        self._first_audio_at: float | None = None
        self._response_start_at: float | None = None
        self._filler_task: asyncio.Task[None] | None = None
        self._tts_gain = 1.0

        self._utterance_queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=1)
        self._listen_task: asyncio.Task[None] | None = None
        self._operator_server: OperatorServer | None = None

        # Audio output stream (persistent, avoids open/close per chunk)
        self._output_stream: sd.OutputStream | None = None
        self._started = False
        self._telemetry: dict[str, float] = {
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
        }
        self._telemetry_error_counts: dict[str, float] = {}
        self._conversation_traces: deque[dict[str, Any]] = deque(maxlen=CONVERSATION_TRACE_MAXLEN)
        self._turn_trace_seq = 0
        self._episodic_timeline: deque[dict[str, Any]] = deque(maxlen=EPISODIC_TIMELINE_MAXLEN)
        self._episode_seq = 0
        self._voice_user_profiles: dict[str, dict[str, str]] = {}
        self._last_learned_preferences: dict[str, Any] = {}
        self._active_control_preset = "custom"
        self._personality_preview_snapshot: dict[str, str] | None = None
        self._stt_diagnostics: dict[str, Any] = self._default_stt_diagnostics()
        self._runtime_invariant_checked_at = 0.0
        self._runtime_invariant_checked_monotonic = 0.0
        self._runtime_invariant_violations_total = 0
        self._runtime_invariant_auto_heals_total = 0
        self._runtime_invariant_recent: deque[dict[str, Any]] = deque(maxlen=RUNTIME_INVARIANT_HISTORY_MAXLEN)
        self._load_runtime_state()
        self._publish_voice_status()
        self._publish_skills_status()
        self._publish_observability_status()

    def start(self) -> None:
        """Initialize all subsystems."""
        if self._started:
            return
        self._started = True
        try:
            blockers = self._startup_blockers()
            if blockers:
                raise RuntimeError("; ".join(blockers))

            with suppress(Exception):
                self._skills.discover()
            self._publish_skills_status()

            observability = getattr(self, "_observability", None)
            if observability is not None:
                observability.start()
                observability.record_event("startup", {"mode": "simulation" if self.robot.sim else "hardware"})
                self._publish_observability_status()

            self.robot.connect()
            if self.config.motion_enabled:
                self.presence.start()

            self._use_robot_audio = not self.robot.sim

            if not self.args.no_vision and not self.robot.sim:
                from jarvis.vision.face_tracker import FaceTracker
                self.face_tracker = FaceTracker(
                    presence=self.presence,
                    get_frame=self.robot.get_frame,
                    model_path=self.config.yolo_model,
                    fps=self.config.face_track_fps,
                )
                self.face_tracker.start()

                if self.config.hand_track_enabled:
                    from jarvis.vision.hand_tracker import HandTracker
                    self.hand_tracker = HandTracker(
                        presence=self.presence,
                        get_frame=self.robot.get_frame,
                        fps=self.config.face_track_fps,
                    )
                    self.hand_tracker.start()

            if self._use_robot_audio:
                self.robot.start_audio(recording=True, playing=self.tts is not None)
                time.sleep(0.2)  # give media pipelines a moment to warm up
                self._robot_input_sr = self.robot.get_input_audio_samplerate() or self.config.sample_rate
                self._robot_output_sr = self.robot.get_output_audio_samplerate() or self.config.sample_rate
                log.info(
                    "Using Reachy Mini media audio (in=%dHz out=%dHz)",
                    self._robot_input_sr,
                    self._robot_output_sr,
                )
            else:
                if self.tts is not None:
                    _require_sounddevice("local audio playback")
                    # Open persistent audio output stream
                    self._output_stream = sd.OutputStream(
                        samplerate=self.config.sample_rate,
                        channels=1,
                        dtype="float32",
                    )
                    self._output_stream.start()

            log.info("Jarvis is online.")
            self._publish_voice_status()
            self._publish_observability_status()
        except Exception:
            self.stop()
            raise

    def _startup_summary_lines(self) -> list[str]:
        tts_enabled = bool(self.tts is not None)
        tts_reason = "enabled" if tts_enabled else "disabled (no ELEVENLABS_API_KEY or --no-tts)"
        memory_state = "enabled" if self.config.memory_enabled else "disabled"
        warning_count = len(getattr(self.config, "startup_warnings", []))
        voice = getattr(self, "_voice_attention", None)
        wake_mode = getattr(voice, "mode", "always_listening")
        timeout_profile = getattr(voice, "timeout_profile", "normal")
        skills = getattr(self, "_skills", None)
        skills_enabled = bool(skills.enabled) if skills is not None else False
        observability = getattr(self, "_observability", None)
        operator_auth_mode = _runtime_normalize_operator_auth_mode(
            getattr(self.config, "operator_auth_mode", "token"),
            valid_modes=VALID_OPERATOR_AUTH_MODES,
        )
        operator_token_set = bool(str(getattr(self.config, "operator_auth_token", "")).strip())
        operator_auth_risk = _runtime_operator_auth_risk(
            auth_mode=operator_auth_mode,
            token_configured=operator_token_set,
        )
        operator_auth = f"mode={operator_auth_mode} risk={operator_auth_risk}"
        if operator_auth_mode in {"token", "session"}:
            operator_auth = f"{operator_auth} token={'set' if operator_token_set else 'missing'}"
        return [
            f"Mode: {'simulation' if self.robot.sim else 'hardware'}",
            f"Motion: {'on' if self.config.motion_enabled else 'off'} | Vision: {'on' if not self.args.no_vision and not self.robot.sim else 'off'} | Hands: {'on' if self.config.hand_track_enabled else 'off'}",
            f"Home tools: {'on' if self.config.home_enabled else 'off'}",
            f"Safe mode: {'on' if bool(getattr(self.config, 'safe_mode_enabled', False)) else 'off'}",
            f"Home conversation: {'on' if self.config.home_conversation_enabled else 'off'}",
            f"Wake mode: {wake_mode} | calibration: {getattr(self.config, 'wake_calibration_profile', 'default')} | timeout profile: {timeout_profile}",
            f"TTS: {tts_reason}",
            f"Memory: {memory_state} ({self.config.memory_path})",
            f"Skills: {'on' if skills_enabled else 'off'} ({getattr(self.config, 'skills_dir', 'n/a')})",
            f"Operator server: {'on' if getattr(self.config, 'operator_server_enabled', False) else 'off'} ({getattr(self.config, 'operator_server_host', '127.0.0.1')}:{getattr(self.config, 'operator_server_port', 0)}; {operator_auth})",
            f"Observability: {'on' if observability is not None else 'off'} ({getattr(self.config, 'observability_db_path', 'n/a')})",
            f"Persona style: {self.config.persona_style}",
            f"Config warnings: {warning_count}",
            f"Tool policy: allow={len(self.config.tool_allowlist)} deny={len(self.config.tool_denylist)}",
            f"Error taxonomy: total={len(TOOL_SERVICE_ERROR_CODES)} service={len(TELEMETRY_SERVICE_ERROR_DETAILS)} storage={len(TELEMETRY_STORAGE_ERROR_DETAILS)}",
        ]

    def _publish_voice_status(self) -> None:
        self._check_runtime_invariants(auto_heal=True)
        voice = self._voice_controller()
        status = voice.status()
        try:
            state = self.presence.signals.state
            status["presence_state"] = str(state.value)
            self._apply_turn_choreography(state)
        except Exception:
            status["presence_state"] = "unknown"
        status["turn_choreography"] = self._turn_choreography_snapshot()
        status["stt_diagnostics"] = self._stt_diagnostics_snapshot()
        status["voice_profile_user"] = self._active_voice_user()
        status["voice_profile"] = self._active_voice_profile()
        status["voice_profile_count"] = len(getattr(self, "_voice_user_profiles", {}))
        status["control_preset"] = str(getattr(self, "_active_control_preset", "custom"))
        last_doa_update = float(getattr(self, "_last_doa_update", 0.0) or 0.0)
        now_mono = time.monotonic()
        doa_age_sec = 0.0
        if last_doa_update:
            doa_age_sec = max(0.0, now_mono - last_doa_update)
        attention_source = "unknown"
        with suppress(Exception):
            attention_source = str(self.presence.attention_source())
        status["acoustic_scene"] = {
            "last_doa_angle": getattr(self, "_last_doa_angle", None),
            "last_doa_speech": getattr(self, "_last_doa_speech", None),
            "last_doa_age_sec": doa_age_sec,
            "attention_confidence": self._attention_confidence(now_mono),
            "attention_source": attention_source,
        }
        last_learned_preferences = getattr(self, "_last_learned_preferences", {})
        status["preference_learning"] = (
            dict(last_learned_preferences)
            if isinstance(last_learned_preferences, dict)
            else {}
        )
        status["multimodal_grounding"] = self._multimodal_grounding_snapshot()
        set_runtime_voice_state(status)
        observability = getattr(self, "_observability", None)
        if observability is not None:
            with suppress(Exception):
                observability.record_state_transition(status.get("presence_state", "unknown"), reason="presence_state")

    def _apply_turn_choreography(self, state: State) -> None:
        cues = TURN_CHOREOGRAPHY_CUES.get(state)
        if cues is None:
            return
        label = str(cues.get("label", "unknown"))
        phase = str(state.value)
        current = getattr(self, "_turn_choreography", {})
        if isinstance(current, dict) and current.get("phase") == phase and current.get("label") == label:
            return
        signals = getattr(self.presence, "signals", None)
        if signals is None:
            return
        turn_lean = float(cues.get("turn_lean", 0.0))
        turn_tilt = float(cues.get("turn_tilt", 0.0))
        turn_glance_yaw = float(cues.get("turn_glance_yaw", 0.0))
        signals.turn_lean = turn_lean
        signals.turn_tilt = turn_tilt
        signals.turn_glance_yaw = turn_glance_yaw
        updated_at = time.time()
        self._turn_choreography = {
            "phase": phase,
            "label": label,
            "turn_lean": turn_lean,
            "turn_tilt": turn_tilt,
            "turn_glance_yaw": turn_glance_yaw,
            "updated_at": updated_at,
        }
        observability = getattr(self, "_observability", None)
        if observability is not None:
            with suppress(Exception):
                observability.record_event(
                    "turn_choreography",
                    {
                        "phase": phase,
                        "label": label,
                        "turn_lean": turn_lean,
                        "turn_tilt": turn_tilt,
                        "turn_glance_yaw": turn_glance_yaw,
                    },
                )

    def _turn_choreography_snapshot(self) -> dict[str, Any]:
        current = getattr(self, "_turn_choreography", None)
        if isinstance(current, dict):
            return {str(key): value for key, value in current.items()}
        return {
            "phase": str(State.IDLE.value),
            "label": "idle_reset",
            "turn_lean": 0.0,
            "turn_tilt": 0.0,
            "turn_glance_yaw": 0.0,
            "updated_at": 0.0,
        }

    def _publish_skills_status(self) -> None:
        skills = getattr(self, "_skills", None)
        if skills is None:
            set_runtime_skills_state({"enabled": False, "loaded_count": 0, "enabled_count": 0, "skills": []})
            return
        set_runtime_skills_state(skills.status_snapshot())

    def _publish_observability_status(self) -> None:
        observability = getattr(self, "_observability", None)
        if observability is None:
            set_runtime_observability_state(_runtime_default_observability_status_snapshot())
            return
        try:
            snapshot = observability.status_snapshot()
        except Exception:
            snapshot = _runtime_default_observability_status_snapshot()
        if isinstance(snapshot, dict):
            snapshot["latency_dashboards"] = self._conversation_latency_analytics()
            snapshot["policy_decision_analytics"] = self._policy_decision_analytics()
        set_runtime_observability_state(snapshot)

    def _operator_control_schema(self) -> dict[str, Any]:
        return _runtime_operator_control_schema(
            valid_wake_modes=VALID_WAKE_MODES,
            valid_timeout_profiles=VALID_TIMEOUT_PROFILES,
            valid_persona_styles=VALID_PERSONA_STYLES,
            valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
            valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
            valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
            valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
            valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
            valid_control_presets=VALID_CONTROL_PRESETS,
        )

    def _operator_available_actions(self) -> list[str]:
        schema = self._operator_control_schema()
        actions = schema.get("actions")
        if not isinstance(actions, dict):
            return []
        return sorted(str(name) for name in actions)

    def _startup_blockers(self) -> list[str]:
        return _runtime_startup_blockers(
            config=self.config,
            args=self.args,
            valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        )

    def _load_runtime_state(self) -> None:
        _runtime_load_runtime_state(
            self,
            episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
            valid_persona_styles=VALID_PERSONA_STYLES,
            valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
            valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
            valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
            valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
            valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
            valid_control_presets=VALID_CONTROL_PRESETS,
            set_safe_mode_fn=service_tools.set_safe_mode,
        )

    def _save_runtime_state(self) -> None:
        _runtime_save_runtime_state(
            self,
            episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
            valid_persona_styles=VALID_PERSONA_STYLES,
            valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
        )

    def _voice_controller(self) -> VoiceAttentionController:
        voice = getattr(self, "_voice_attention", None)
        if voice is not None:
            return voice
        fallback = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
        self._voice_attention = fallback
        return fallback

    def _active_voice_user(self) -> str:
        return _runtime_active_voice_user(self)

    def _active_voice_profile(self, *, user: str | None = None) -> dict[str, str]:
        return _runtime_active_voice_profile(
            self,
            user=user,
            valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
            valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
            valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
            valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
        )

    def _with_voice_profile_guidance(self, text: str) -> str:
        return _runtime_with_voice_profile_guidance(
            self,
            text,
            valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
            valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
            valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
            valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
        )

    def _learn_voice_preferences(
        self,
        text: str,
        *,
        now_ts: float | None = None,
    ) -> dict[str, str]:
        updates = _runtime_detect_voice_profile_updates(text)
        if not updates:
            return {}

        normalized: dict[str, str] = {}
        verbosity = self._parse_control_choice(
            updates.get("verbosity"),
            VALID_VOICE_PROFILE_VERBOSITY,
        )
        if verbosity is not None:
            normalized["verbosity"] = verbosity
        confirmations = self._parse_control_choice(
            updates.get("confirmations"),
            VALID_VOICE_PROFILE_CONFIRMATIONS,
        )
        if confirmations is not None:
            normalized["confirmations"] = confirmations
        pace = self._parse_control_choice(
            updates.get("pace"),
            VALID_VOICE_PROFILE_PACE,
        )
        if pace is not None:
            normalized["pace"] = pace
        tone = self._parse_control_choice(
            updates.get("tone"),
            VALID_VOICE_PROFILE_TONE,
        )
        if tone is not None:
            normalized["tone"] = tone
        if not normalized:
            return {}

        user = self._active_voice_user()
        profile = self._active_voice_profile(user=user)
        profile.update(normalized)
        self._voice_user_profiles[user] = profile

        applied_at = time.time() if now_ts is None else float(now_ts)
        self._telemetry["preference_update_turns"] = (
            float(self._telemetry.get("preference_update_turns", 0.0) or 0.0) + 1.0
        )
        self._telemetry["preference_update_fields"] = (
            float(self._telemetry.get("preference_update_fields", 0.0) or 0.0)
            + float(len(normalized))
        )
        self._last_learned_preferences = {
            "user": user,
            "updates": dict(normalized),
            "applied_at": applied_at,
            "source_text": str(text).strip()[:160],
        }

        memory = getattr(self.brain, "_memory", None)
        if memory is not None:
            with suppress(Exception):
                memory.upsert_summary(
                    f"voice_profile:{user}",
                    _runtime_voice_profile_summary(profile),
                )

        self._persist_runtime_state_safe()
        self._publish_voice_status()
        return normalized

    def _runtime_invariant_snapshot(self) -> dict[str, Any]:
        return _runtime_runtime_invariant_snapshot(self)

    def _check_runtime_invariants(self, *, auto_heal: bool = True) -> dict[str, Any]:
        return _runtime_check_runtime_invariants(
            self,
            auto_heal=auto_heal,
            runtime_invariant_history_maxlen=RUNTIME_INVARIANT_HISTORY_MAXLEN,
            valid_control_presets=VALID_CONTROL_PRESETS,
        )

    _percentile = staticmethod(_runtime_percentile)

    def _conversation_latency_analytics(self) -> dict[str, Any]:
        traces = list(getattr(self, "_conversation_traces", []))
        return _runtime_conversation_latency_analytics(traces)

    def _policy_decision_analytics(self) -> dict[str, Any]:
        traces = list(getattr(self, "_conversation_traces", []))
        return _runtime_policy_decision_analytics(traces)

    def _runtime_profile_snapshot(self) -> dict[str, Any]:
        return _runtime_runtime_profile_snapshot(self)

    def _apply_runtime_profile(self, profile: dict[str, Any], *, mark_custom: bool = True) -> dict[str, Any]:
        return _runtime_apply_runtime_profile(
            self,
            profile,
            mark_custom=mark_custom,
            valid_wake_modes=VALID_WAKE_MODES,
            valid_timeout_profiles=VALID_TIMEOUT_PROFILES,
            valid_persona_styles=VALID_PERSONA_STYLES,
            valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
            valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
            valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
            valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
            valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
            set_safe_mode_fn=service_tools.set_safe_mode,
        )

    def _preset_profile(self, preset: str) -> dict[str, Any]:
        return _runtime_preset_profile(self, preset)

    def _apply_control_preset(self, preset: str) -> dict[str, Any] | None:
        return _runtime_apply_control_preset(
            self,
            preset,
            valid_control_presets=VALID_CONTROL_PRESETS,
        )

    def _refresh_tool_error_counters(self) -> None:
        try:
            recent = list_summaries(limit=200)
        except Exception:
            return
        (
            service_errors,
            storage_errors,
            unknown_summary_details,
            per_code,
        ) = _runtime_summarize_tool_error_counters(
            recent,
            tool_service_error_codes=TOOL_SERVICE_ERROR_CODES,
            storage_error_details=TELEMETRY_STORAGE_ERROR_DETAILS,
            service_error_details=TELEMETRY_SERVICE_ERROR_DETAILS,
        )
        self._telemetry["service_errors"] = service_errors
        self._telemetry["storage_errors"] = storage_errors
        self._telemetry["unknown_summary_details"] = unknown_summary_details
        self._telemetry_error_counts = per_code

    def _telemetry_snapshot(self) -> dict[str, Any]:
        return _runtime_telemetry_snapshot(
            self._telemetry,
            telemetry_error_counts=getattr(self, "_telemetry_error_counts", {}),
        )

    _default_stt_diagnostics = staticmethod(_runtime_default_stt_diagnostics)
    _stt_confidence_band = staticmethod(_runtime_stt_confidence_band)

    def _stt_diagnostics_snapshot(self) -> dict[str, Any]:
        return _runtime_stt_diagnostics_snapshot(getattr(self, "_stt_diagnostics", None))

    _transcribe_with_optional_diagnostics = staticmethod(_runtime_transcribe_with_optional_diagnostics)

    def _update_stt_diagnostics(
        self,
        *,
        text: str,
        source: str,
        fallback_used: bool,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self._stt_diagnostics = _runtime_update_stt_diagnostics(
            text=text,
            source=source,
            fallback_used=fallback_used,
            diagnostics=diagnostics,
        )

    def _transcribe_with_fallback(self, audio: np.ndarray) -> str:
        return _runtime_transcribe_with_fallback(self, audio)

    def _publish_observability_snapshot(self, *, force: bool = False) -> None:
        observability = getattr(self, "_observability", None)
        if observability is None:
            return
        now = time.monotonic()
        if not force and (now - self._last_observability_snapshot_at) < self.config.observability_snapshot_interval_sec:
            return
        self._last_observability_snapshot_at = now
        snapshot = self._telemetry_snapshot()
        with suppress(Exception):
            observability.record_snapshot(snapshot)
        with suppress(Exception):
            observability.record_tool_summaries(list_summaries(limit=100))
        alerts = []
        with suppress(Exception):
            alerts = observability.detect_failure_burst(window_sec=300.0)
        if alerts:
            log.warning("Observability alerts: %s", alerts)
        self._publish_observability_status()

    async def _watchdog_loop(self) -> None:
        state_name = str(getattr(self.presence.signals.state, "value", "unknown")).lower()
        state_since = time.monotonic()
        while True:
            now = time.monotonic()
            if (now - float(getattr(self, "_runtime_invariant_checked_monotonic", 0.0))) >= 2.0:
                with suppress(Exception):
                    self._check_runtime_invariants(auto_heal=True)
            current = str(getattr(self.presence.signals.state, "value", "unknown")).lower()
            if current != state_name:
                state_name = current
                state_since = now
            timeout = None
            if current == str(State.LISTENING.value):
                timeout = self.config.watchdog_listening_timeout_sec
            elif current == str(State.THINKING.value):
                timeout = self.config.watchdog_thinking_timeout_sec
            elif current == str(State.SPEAKING.value):
                timeout = self.config.watchdog_speaking_timeout_sec
            if timeout is not None and (now - state_since) > timeout:
                log.warning("Watchdog reset triggered for state=%s", current)
                self.presence.signals.state = State.IDLE
                self._barge_in.set()
                self._flush_output()
                self._clear_tts_queue()
                self._barge_in.clear()
                self._telemetry["fallback_responses"] += 1.0
                observability = getattr(self, "_observability", None)
                if observability is not None:
                    with suppress(Exception):
                        observability.record_event(
                            "watchdog_reset",
                            {"state": current, "timeout_sec": timeout},
                        )
                state_name = str(State.IDLE.value)
                state_since = now
            await asyncio.sleep(WATCHDOG_POLL_SEC)

    async def _operator_status_provider(self) -> dict[str, Any]:
        return await _runtime_operator_status_provider(
            self,
            valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
            valid_control_presets=VALID_CONTROL_PRESETS,
            system_status_fn=service_tools.system_status,
        )

    def _startup_diagnostics_provider(self) -> list[str]:
        warnings = list(getattr(self.config, "startup_warnings", []))
        blockers = self._startup_blockers()
        return [*warnings, *[f"BLOCKER: {item}" for item in blockers]]

    def _operator_metrics_provider(self) -> str:
        observability = getattr(self, "_observability", None)
        if observability is None:
            return ""
        with suppress(Exception):
            return observability.prometheus_metrics()
        return ""

    def _operator_events_provider(self) -> list[dict[str, Any]]:
        observability = getattr(self, "_observability", None)
        if observability is None:
            return []
        with suppress(Exception):
            return observability.recent_events(limit=100)
        return []

    _parse_control_bool = staticmethod(_runtime_parse_control_bool)
    _parse_control_choice = staticmethod(_runtime_parse_control_choice)
    _parse_memory_correction_command = staticmethod(_runtime_parse_memory_correction_command)
    _classify_user_intent = staticmethod(_turn_classify_user_intent)
    _looks_like_user_correction = staticmethod(_turn_looks_like_user_correction)

    def _is_followup_carryover_candidate(self, text: str, *, now_ts: float | None = None) -> bool:
        context = getattr(self, "_followup_carryover", {})
        return _turn_is_followup_carryover_candidate(
            text,
            context=context,
            now_ts=now_ts,
        )

    def _with_followup_carryover(self, text: str, *, now_ts: float | None = None) -> tuple[str, bool]:
        context = getattr(self, "_followup_carryover", {})
        return _turn_with_followup_carryover(
            text,
            context=context,
            now_ts=now_ts,
        )

    def _update_followup_carryover(
        self,
        text: str,
        intent_class: str,
        *,
        resolved: bool | None,
        now_ts: float | None = None,
    ) -> None:
        payload = _turn_update_followup_carryover(
            text,
            intent_class,
            resolved=resolved,
            now_ts=now_ts,
        )
        if payload is not None:
            self._followup_carryover = payload

    @staticmethod
    def _turn_tool_summaries_since(started_at: float) -> list[dict[str, Any]]:
        return _turn_tool_summaries_since(
            started_at,
            list_summaries_fn=list_summaries,
        )

    _completion_success_from_summaries = staticmethod(_turn_completion_success_from_summaries)
    _tool_call_trace_items = staticmethod(_turn_tool_call_trace_items)
    _policy_decisions_from_summaries = staticmethod(_turn_policy_decisions_from_summaries)

    def _record_conversation_trace(
        self,
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
    ) -> None:
        _runtime_record_conversation_trace(
            self,
            user_text=user_text,
            intent_class=intent_class,
            turn_started_at=turn_started_at,
            stt_latency_ms=stt_latency_ms,
            llm_first_sentence_ms=llm_first_sentence_ms,
            tts_first_audio_ms=tts_first_audio_ms,
            response_success=response_success,
            tool_summaries=tool_summaries,
            lifecycle=lifecycle,
            used_brain_response=used_brain_response,
            followup_carryover_applied=followup_carryover_applied,
            preference_updates=preference_updates,
            multimodal_grounding=multimodal_grounding,
            episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
        )

    def _record_episodic_snapshot(self, trace_item: dict[str, Any]) -> None:
        _runtime_record_episodic_snapshot(
            self,
            trace_item,
            episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
        )

    def _operator_episodic_timeline_provider(self, limit: int = 20) -> list[dict[str, Any]]:
        return _runtime_operator_episodic_timeline_provider(self, limit=limit)

    def _operator_conversation_trace_provider(self, limit: int = 20) -> list[dict[str, Any]]:
        return _runtime_operator_conversation_trace_provider(self, limit=limit)

    def _persist_runtime_state_safe(self) -> None:
        with suppress(Exception):
            self._save_runtime_state()

    def _set_persona_style(self, style: str) -> None:
        self.config.persona_style = style
        brain = getattr(self, "brain", None)
        memory = getattr(brain, "_memory", None)
        if memory is not None:
            with suppress(Exception):
                memory.upsert_summary("persona_style", style)

    async def _operator_control_handler(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await _runtime_handle_operator_control(self, action, payload)

    async def _start_operator_server(self) -> None:
        if not self.config.operator_server_enabled:
            return
        if self._operator_server is not None:
            return
        server = OperatorServer(
            host=self.config.operator_server_host,
            port=self.config.operator_server_port,
            status_provider=self._operator_status_provider,
            diagnostics_provider=self._startup_diagnostics_provider,
            control_handler=self._operator_control_handler,
            control_schema_provider=self._operator_control_schema,
            metrics_provider=self._operator_metrics_provider,
            events_provider=self._operator_events_provider,
            conversation_trace_provider=self._operator_conversation_trace_provider,
            inbound_callback=lambda payload, headers, path, source: service_tools.record_inbound_webhook_event(
                payload=payload,
                headers=headers,
                path=path,
                source=source,
            ),
            inbound_enabled=self.config.webhook_inbound_enabled,
            inbound_token=self.config.webhook_inbound_token or self.config.webhook_auth_token,
            operator_auth_mode=self.config.operator_auth_mode,
            operator_auth_token=self.config.operator_auth_token,
        )
        try:
            await server.start()
        except Exception as exc:
            log.warning("Operator server failed to start: %s", exc)
            return
        self._operator_server = server
        observability = getattr(self, "_observability", None)
        if observability is not None:
            with suppress(Exception):
                observability.record_event(
                    "operator_server_started",
                    {
                        "host": self.config.operator_server_host,
                        "port": self.config.operator_server_port,
                    },
                )

    async def _stop_operator_server(self) -> None:
        server = getattr(self, "_operator_server", None)
        if server is None:
            return
        with suppress(Exception):
            await server.stop()
        self._operator_server = None

    def stop(self) -> None:
        """Shut down all subsystems."""
        if not self._started:
            return
        self._save_runtime_state()
        observability = getattr(self, "_observability", None)
        if observability is not None:
            self._publish_observability_snapshot(force=True)
            with suppress(Exception):
                observability.record_event("shutdown", {"reason": "stop_called"})
            with suppress(Exception):
                observability.stop()
            with suppress(Exception):
                observability.close()
        if self._output_stream:
            with suppress(Exception):
                self._output_stream.stop()
            with suppress(Exception):
                self._output_stream.close()
            self._output_stream = None
        if self.face_tracker:
            with suppress(Exception):
                self.face_tracker.stop()
            self.face_tracker = None
        if self._use_robot_audio:
            with suppress(Exception):
                self.robot.stop_audio(recording=True, playing=True)
        if self.hand_tracker:
            with suppress(Exception):
                self.hand_tracker.stop()
            self.hand_tracker = None
        if self.config.motion_enabled:
            with suppress(Exception):
                self.presence.stop()
        with suppress(Exception):
            self.robot.disconnect()
        self._started = False
        set_runtime_voice_state(
            {
                "mode": "offline",
                "followup_active": False,
                "sleeping": False,
                "active_room": "unknown",
                "stt_diagnostics": self._default_stt_diagnostics(),
            }
        )
        self._publish_observability_status()
        self._publish_skills_status()
        log.info("Jarvis offline.")

    async def run(self) -> None:
        await _runtime_run(self)

    async def _enqueue_utterance(self, audio: np.ndarray) -> None:
        try:
            self._utterance_queue.put_nowait(audio)
        except asyncio.QueueFull:
            with suppress(asyncio.QueueEmpty):
                self._utterance_queue.get_nowait()
            await self._utterance_queue.put(audio)

    async def _listen_loop(self) -> None:
        await _runtime_listen_loop(
            self,
            require_sounddevice_fn=_require_sounddevice,
            sd_module=sd,
            to_mono_fn=_to_mono,
            resample_audio_fn=_resample_audio,
            chunk_samples=CHUNK_SAMPLES,
            min_utterance=MIN_UTTERANCE,
        )

    def _flush_output(self) -> None:
        if self._use_robot_audio:
            self.robot.flush_audio_output()
            return

        if self._output_stream is None:
            return

        try:
            self._output_stream.abort()
        except Exception:
            try:
                self._output_stream.stop()
            except Exception:
                pass

        try:
            self._output_stream.start()
        except Exception:
            pass

    def _play_audio_chunk(self, audio_16k: np.ndarray) -> None:
        if audio_16k.size == 0:
            return

        if self._use_robot_audio:
            audio_out = audio_16k
            if self._robot_output_sr != self.config.sample_rate:
                audio_out = _resample_audio(audio_16k, self.config.sample_rate, self._robot_output_sr)
            self.robot.push_audio_sample(audio_out)
            return

        if self._output_stream is not None:
            try:
                self._output_stream.write(audio_16k.reshape(-1, 1))
            except Exception as e:
                log.warning("Audio output write failed: %s", e)

    async def _respond_and_speak(self, text: str) -> None:
        await _runtime_respond_and_speak(self, text)

    async def _tts_loop(self) -> None:
        """Consume sentences and play TTS in order, with barge-in support."""
        assert self.tts is not None
        while True:
            response_id, sentence, is_filler, pause = await self._tts_queue.get()
            if self._barge_in.is_set():
                self._flush_output()
                self.presence.signals.speech_energy = 0.0
                continue

            if not getattr(self, "_tts_output_enabled", True):
                if not is_filler:
                    print(f"  JARVIS: {sentence}")
                if pause > 0:
                    await asyncio.sleep(pause)
                continue

            try:
                async for audio_chunk in self.tts.stream_chunks_async(sentence):
                    if self._barge_in.is_set():
                        self._flush_output()
                        self.presence.signals.speech_energy = 0.0
                        break
                    if not is_filler and response_id == self._active_response_id and self._first_audio_at is None:
                        self._first_audio_at = time.monotonic()
                        if self._response_start_at is not None:
                            latency_ms = (self._first_audio_at - self._response_start_at) * 1000.0
                            self._telemetry["tts_first_audio_total_ms"] += latency_ms
                            self._telemetry["tts_first_audio_count"] += 1.0
                            log.info(
                                "TTS first audio latency: %.0fms",
                                latency_ms,
                            )
                    self.presence.signals.speech_energy = float(
                        max(0.0, min(1.0, float(np.sqrt(np.mean(audio_chunk ** 2)) * 5.0)))
                    )
                    normalized = self._normalize_tts_chunk(audio_chunk)
                    self._play_audio_chunk(normalized)
                    await asyncio.sleep(0)
            except Exception as e:
                log.warning("TTS loop failed for sentence chunk: %s", e)
                config = getattr(self, "config", None)
                if bool(getattr(config, "tts_fallback_text_only", True)) and not is_filler:
                    print(f"  JARVIS: {sentence}")
                    telemetry = getattr(self, "_telemetry", None)
                    if isinstance(telemetry, dict):
                        telemetry["fallback_responses"] = float(telemetry.get("fallback_responses", 0.0) or 0.0) + 1.0
                    observability = getattr(self, "_observability", None)
                    if observability is not None:
                        with suppress(Exception):
                            observability.record_event(
                                "tts_fallback_text_only",
                                {"sentence_len": len(sentence)},
                            )
            self.presence.signals.speech_energy = 0.0
            if pause > 0:
                await asyncio.sleep(pause)

    def _clear_tts_queue(self) -> None:
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _compute_turn_taking(
        self,
        conf: float,
        doa_speech: bool | None,
        assistant_busy: bool,
        now: float,
    ) -> bool:
        attention = 0.0
        if self.presence.signals.face_last_seen and (now - self.presence.signals.face_last_seen) <= ATTENTION_RECENCY_SEC:
            attention = 1.0
        elif self.presence.signals.hand_last_seen and (now - self.presence.signals.hand_last_seen) <= ATTENTION_RECENCY_SEC:
            attention = 0.8
        elif self.presence.signals.doa_last_seen and (now - self.presence.signals.doa_last_seen) <= ATTENTION_RECENCY_SEC:
            attention = 0.5

        doa_score = 1.0 if doa_speech else 0.0
        score = (0.55 * conf) + (0.3 * doa_score) + (0.15 * attention)
        if assistant_busy:
            threshold = self._voice_controller().barge_in_threshold()
        else:
            threshold = TURN_TAKING_THRESHOLD

        if assistant_busy:
            if doa_speech is True:
                return score >= (threshold - 0.05)
            if conf >= 0.8 and attention >= 0.8:
                return True
            if conf < 0.35 and attention < 0.6 and doa_speech is False:
                return False

        if conf >= 0.9 and attention >= 0.8:
            return True
        if conf < 0.25 and attention < 0.5 and doa_speech is False:
            return False
        return score >= threshold

    def _attention_confidence(self, now: float) -> float:
        signals = getattr(self.presence, "signals", None)
        if signals is None:
            return 0.0
        face_last_seen = getattr(signals, "face_last_seen", None)
        hand_last_seen = getattr(signals, "hand_last_seen", None)
        doa_last_seen = getattr(signals, "doa_last_seen", None)
        if face_last_seen and (now - face_last_seen) <= ATTENTION_RECENCY_SEC:
            return 1.0
        if hand_last_seen and (now - hand_last_seen) <= ATTENTION_RECENCY_SEC:
            return 0.8
        if doa_last_seen and (now - doa_last_seen) <= ATTENTION_RECENCY_SEC:
            return 0.5
        return 0.0

    def _multimodal_grounding_snapshot(self) -> dict[str, Any]:
        signals = getattr(self.presence, "signals", None)
        now_mono = time.monotonic()
        face_age_sec: float | None = None
        hand_age_sec: float | None = None
        doa_age_sec: float | None = None
        if signals is not None:
            face_last_seen = getattr(signals, "face_last_seen", None)
            hand_last_seen = getattr(signals, "hand_last_seen", None)
            doa_last_seen = getattr(signals, "doa_last_seen", None)
            if face_last_seen:
                face_age_sec = max(0.0, now_mono - float(face_last_seen))
            if hand_last_seen:
                hand_age_sec = max(0.0, now_mono - float(hand_last_seen))
            if doa_last_seen:
                doa_age_sec = max(0.0, now_mono - float(doa_last_seen))
        attention_source = "unknown"
        with suppress(Exception):
            attention_source = str(self.presence.attention_source())
        return _runtime_multimodal_grounding_snapshot(
            face_age_sec=face_age_sec,
            hand_age_sec=hand_age_sec,
            doa_age_sec=doa_age_sec,
            doa_angle=getattr(self, "_last_doa_angle", None),
            doa_speech=getattr(self, "_last_doa_speech", None),
            stt_diagnostics=self._stt_diagnostics_snapshot(),
            attention_confidence=self._attention_confidence(now_mono),
            attention_source=attention_source,
            recency_threshold_sec=ATTENTION_RECENCY_SEC,
        )

    @staticmethod
    def _repair_prompt(text: str) -> str:
        excerpt = " ".join(str(text or "").split())
        if len(excerpt) > 140:
            excerpt = excerpt[:137].rstrip() + "..."
        return REPAIR_CONFIRMATION_TEMPLATE.format(text=excerpt)

    def _requires_stt_repair(self, text: str, intent_class: str) -> bool:
        if intent_class not in {"action", "hybrid"}:
            return False
        phrase = str(text or "").strip()
        if not phrase:
            return False
        if self._looks_like_user_correction(phrase):
            return False
        words = re.findall(r"[a-z0-9']+", phrase.lower())
        if len(words) < REPAIR_MIN_WORDS:
            return False
        diagnostics = self._stt_diagnostics_snapshot()
        confidence_band = str(diagnostics.get("confidence_band", "unknown")).strip().lower()
        try:
            confidence_score = float(diagnostics.get("confidence_score", 0.0))
        except (TypeError, ValueError):
            confidence_score = 0.0
        if not math.isfinite(confidence_score):
            confidence_score = 0.0
        if confidence_band == "low":
            return True
        if confidence_band == "unknown" and confidence_score <= 0.0:
            return bool(diagnostics.get("fallback_used", False))
        return confidence_score < REPAIR_CONFIDENCE_THRESHOLD

    def _requires_confirmation(self, now: float) -> bool:
        attention = self._attention_confidence(now)
        profile = self._active_voice_profile()
        confirmations = profile.get("confirmations", "standard")
        attention_threshold = INTENDED_QUERY_MIN_ATTENTION
        if confirmations == "minimal":
            attention_threshold = 0.15
        elif confirmations == "strict":
            attention_threshold = 0.55
        if attention >= attention_threshold:
            return False
        if confirmations != "strict" and self._last_doa_speech is True:
            return False
        return True

    async def _thinking_filler(self) -> None:
        await asyncio.sleep(THINKING_FILLER_DELAY)
        if self._barge_in.is_set() or self._response_started:
            return
        if self.tts is None:
            return
        await self._tts_queue.put((self._active_response_id, THINKING_FILLER_TEXT, True, 0.0))

    def _normalize_tts_chunk(self, chunk: np.ndarray) -> np.ndarray:
        normalized, next_gain = _runtime_normalize_tts_chunk(
            chunk,
            tts_gain=float(getattr(self, "_tts_gain", 1.0) or 1.0),
            target_rms=TTS_TARGET_RMS,
            gain_smooth=TTS_GAIN_SMOOTH,
        )
        self._tts_gain = next_gain
        return normalized

    def _confidence_pause(self, sentence: str) -> float:
        pace = self._active_voice_profile().get("pace", "normal")
        return _runtime_confidence_pause(
            sentence,
            low_confidence_words=TTS_LOW_CONFIDENCE_WORDS,
            confidence_pause_sec=TTS_CONFIDENCE_PAUSE_SEC,
            sentence_pause_sec=TTS_SENTENCE_PAUSE_SEC,
            pace=pace,
        )


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)-25s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.backup or args.restore:
        config = Config()
        try:
            if args.backup:
                result = create_backup_bundle(config, args.backup)
            else:
                result = restore_backup_bundle(config, args.restore, overwrite=bool(args.force))
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            raise SystemExit(1) from exc
        print(json.dumps(result, indent=2))
        return

    jarvis = Jarvis(args)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(jarvis.run())

    def shutdown(sig, frame):
        task.cancel()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(task)
    finally:
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()


if __name__ == "__main__":
    main()
