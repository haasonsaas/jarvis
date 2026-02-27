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
from scipy.signal import resample_poly

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
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES, TOOL_STORAGE_ERROR_DETAILS
from jarvis.tools.robot import bind as bind_robot_tools
from jarvis.tools import services as service_tools
from jarvis.tools.services import (
    set_runtime_observability_state,
    set_runtime_skills_state,
    set_runtime_voice_state,
)
from jarvis.tool_summary import list_summaries
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

# Audio constants
SILENCE_TIMEOUT = 0.8   # fallback silence timeout if voice attention controller is unavailable
MIN_UTTERANCE = 0.3     # minimum utterance length in seconds
TURN_TAKING_THRESHOLD = 0.55
TURN_TAKING_BARGE_IN_THRESHOLD = 0.4
ATTENTION_RECENCY_SEC = 1.0
THINKING_FILLER_DELAY = 0.35
THINKING_FILLER_TEXT = "One moment."
TTS_TARGET_RMS = 0.08
TTS_GAIN_SMOOTH = 0.2
TTS_SENTENCE_PAUSE_SEC = 0.12
TTS_CONFIDENCE_PAUSE_SEC = 0.18
TTS_LOW_CONFIDENCE_WORDS = {"maybe", "probably", "might", "not sure", "uncertain", "i think", "i believe"}
INTENDED_QUERY_MIN_ATTENTION = 0.35
CONFIRMATION_PHRASE = "Did you mean me?"
REPAIR_CONFIRMATION_TEMPLATE = 'I may have misheard you as: "{text}". Say confirm to proceed, or repeat your request.'
REPAIR_REPEAT_PROMPT = "Understood. Please repeat your request."
REPAIR_CONFIDENCE_THRESHOLD = 0.45
REPAIR_MIN_WORDS = 2
AFFIRMATIONS = {"yes", "yeah", "yep", "yup", "correct", "affirmative", "sure", "please"}
NEGATIONS = {"no", "nope", "nah", "negative"}
TELEMETRY_LOG_EVERY_TURNS = 5
TELEMETRY_STORAGE_ERROR_DETAILS = TOOL_STORAGE_ERROR_DETAILS
TELEMETRY_SERVICE_ERROR_DETAILS = TOOL_SERVICE_ERROR_CODES - TELEMETRY_STORAGE_ERROR_DETAILS
WATCHDOG_POLL_SEC = 0.05
CONVERSATION_TRACE_MAXLEN = 200
EPISODIC_TIMELINE_MAXLEN = 200
VALID_PERSONA_STYLES = {"terse", "composed", "friendly"}
VALID_BACKCHANNEL_STYLES = {"quiet", "balanced", "expressive"}
VALID_VOICE_PROFILE_VERBOSITY = {"brief", "normal", "detailed"}
VALID_VOICE_PROFILE_CONFIRMATIONS = {"minimal", "standard", "strict"}
VALID_VOICE_PROFILE_PACE = {"slow", "normal", "fast"}
VALID_CONTROL_PRESETS = {"quiet_hours", "demo_mode", "maintenance_mode"}
VALID_OPERATOR_AUTH_MODES = {"off", "token", "session"}
MEMORY_FORGET_RE = re.compile(
    r"^(?:please\s+)?(?:forget|delete|remove)\s+(?:memory\s*)?(?:id\s*)?(?P<memory_id>\d+)\s*$",
    re.IGNORECASE,
)
MEMORY_UPDATE_RE = re.compile(
    r"^(?:please\s+)?(?:update|change|edit)\s+(?:memory\s*)?(?:id\s*)?(?P<memory_id>\d+)\s+(?:to|with)\s+(?P<text>.+)$",
    re.IGNORECASE,
)
ACTION_INTENT_TERMS = {
    "turn",
    "set",
    "open",
    "close",
    "lock",
    "unlock",
    "arm",
    "disarm",
    "play",
    "pause",
    "send",
    "notify",
    "remind",
    "create",
    "update",
    "delete",
    "forget",
    "add",
    "trigger",
}
QUESTION_START_TERMS = {"what", "when", "where", "who", "why", "how", "is", "are", "can", "could", "would", "should"}
CORRECTION_TERMS = {
    "actually",
    "i meant",
    "correction",
    "that's wrong",
    "that is wrong",
    "not that",
    "instead",
    "rather",
    "change that",
}
FOLLOWUP_CARRYOVER_MAX_AGE_SEC = 120.0
FOLLOWUP_CARRYOVER_PREFIX_TERMS = (
    "and ",
    "also ",
    "then ",
    "what about",
    "how about",
    "plus ",
    "as well",
    "same for",
)
FOLLOWUP_CARRYOVER_REFERENCE_TERMS = {"it", "that", "this", "them", "there", "one", "same"}
FOLLOWUP_CARRYOVER_SHORT_REPLY_MAX_WORDS = 8
FOLLOWUP_CARRYOVER_ACK_TERMS = {"yes", "yep", "yeah", "no", "nope", "ok", "okay", "thanks", "thank", "sure"}
RUNTIME_INVARIANT_HISTORY_MAXLEN = 40
TURN_CHOREOGRAPHY_CUES: dict[State, dict[str, float | str]] = {
    State.IDLE: {"label": "idle_reset", "turn_lean": 0.0, "turn_tilt": 0.0, "turn_glance_yaw": 0.0},
    State.LISTENING: {"label": "listen_lean_in", "turn_lean": 1.5, "turn_tilt": -1.0, "turn_glance_yaw": -3.0},
    State.THINKING: {"label": "think_glance_away", "turn_lean": 0.5, "turn_tilt": 2.0, "turn_glance_yaw": 8.0},
    State.SPEAKING: {"label": "answer_lock_on", "turn_lean": 1.0, "turn_tilt": 0.0, "turn_glance_yaw": 0.0},
    State.MUTED: {"label": "muted_privacy", "turn_lean": 0.0, "turn_tilt": 0.0, "turn_glance_yaw": 0.0},
}


def _require_sounddevice(feature: str) -> None:
    if sd is not None:
        return
    detail = f" ({_SOUNDDEVICE_IMPORT_ERROR})" if _SOUNDDEVICE_IMPORT_ERROR else ""
    raise RuntimeError(
        f"sounddevice is unavailable; {feature} requires PortAudio.{detail}"
    )


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert arbitrary audio frame to 1D float32 mono."""
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim == 1:
        return a
    if a.ndim != 2:
        return a.reshape(-1).astype(np.float32, copy=False)

    # Heuristic: if channels appear first, transpose.
    if a.shape[0] <= 8 and a.shape[0] < a.shape[1]:
        a = a.T

    if a.shape[1] == 1:
        return a[:, 0]
    return a.mean(axis=1)


def _resample_audio(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or x.size == 0:
        return x.astype(np.float32, copy=False)

    g = math.gcd(int(sr_in), int(sr_out))
    up = int(sr_out) // g
    down = int(sr_in) // g
    y = resample_poly(x.astype(np.float32, copy=False), up=up, down=down)
    return y.astype(np.float32, copy=False)


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
        }
        self._telemetry_error_counts: dict[str, float] = {}
        self._conversation_traces: deque[dict[str, Any]] = deque(maxlen=CONVERSATION_TRACE_MAXLEN)
        self._turn_trace_seq = 0
        self._episodic_timeline: deque[dict[str, Any]] = deque(maxlen=EPISODIC_TIMELINE_MAXLEN)
        self._episode_seq = 0
        self._voice_user_profiles: dict[str, dict[str, str]] = {}
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
        operator_auth_mode = str(getattr(self.config, "operator_auth_mode", "token")).strip().lower()
        if operator_auth_mode not in VALID_OPERATOR_AUTH_MODES:
            operator_auth_mode = "token"
        operator_token_set = bool(str(getattr(self.config, "operator_auth_token", "")).strip())
        if operator_auth_mode == "off":
            operator_auth_risk = "high"
        elif not operator_token_set:
            operator_auth_risk = "high"
        elif operator_auth_mode == "session":
            operator_auth_risk = "low"
        else:
            operator_auth_risk = "medium"
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
            set_runtime_observability_state(
                {
                    "enabled": False,
                    "uptime_sec": 0.0,
                    "restart_count": 0,
                    "alerts": [],
                    "intent_metrics": {
                        "turn_count": 0.0,
                        "answer_intent_count": 0.0,
                        "action_intent_count": 0.0,
                        "hybrid_intent_count": 0.0,
                        "answer_sample_count": 0.0,
                        "completion_sample_count": 0.0,
                        "answer_quality_success_rate": 0.0,
                        "completion_success_rate": 0.0,
                        "correction_count": 0.0,
                        "correction_frequency": 0.0,
                    },
                    "latency_dashboards": {
                        "sample_count": 0,
                        "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                        "by_intent": {},
                        "by_tool_mix": {},
                        "by_wake_mode": {},
                    },
                    "policy_decision_analytics": {
                        "decision_count": 0,
                        "by_tool": {},
                        "by_status": {},
                        "by_reason": {},
                        "by_user": {},
                        "by_user_tool": {},
                    },
                }
            )
            return
        try:
            snapshot = observability.status_snapshot()
        except Exception:
            snapshot = {
                "enabled": False,
                "uptime_sec": 0.0,
                "restart_count": 0,
                "alerts": [],
                "intent_metrics": {
                    "turn_count": 0.0,
                    "answer_intent_count": 0.0,
                    "action_intent_count": 0.0,
                    "hybrid_intent_count": 0.0,
                    "answer_sample_count": 0.0,
                    "completion_sample_count": 0.0,
                    "answer_quality_success_rate": 0.0,
                    "completion_success_rate": 0.0,
                    "correction_count": 0.0,
                    "correction_frequency": 0.0,
                },
                "latency_dashboards": {
                    "sample_count": 0,
                    "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                    "by_intent": {},
                    "by_tool_mix": {},
                    "by_wake_mode": {},
                },
                "policy_decision_analytics": {
                    "decision_count": 0,
                    "by_tool": {},
                    "by_status": {},
                    "by_reason": {},
                    "by_user": {},
                    "by_user_tool": {},
                },
            }
        if isinstance(snapshot, dict):
            snapshot["latency_dashboards"] = self._conversation_latency_analytics()
            snapshot["policy_decision_analytics"] = self._policy_decision_analytics()
        set_runtime_observability_state(snapshot)

    def _operator_control_schema(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "actions": {
                "set_wake_mode": {"required": ["mode"], "enum": {"mode": sorted(VALID_WAKE_MODES)}},
                "set_sleeping": {"required": ["sleeping"], "types": {"sleeping": "boolean"}},
                "set_timeout_profile": {
                    "required": ["profile"],
                    "enum": {"profile": sorted(VALID_TIMEOUT_PROFILES)},
                },
                "set_push_to_talk": {"required": ["active"], "types": {"active": "boolean"}},
                "set_motion_enabled": {"required": ["enabled"], "types": {"enabled": "boolean"}},
                "set_home_enabled": {"required": ["enabled"], "types": {"enabled": "boolean"}},
                "set_safe_mode": {"required": ["enabled"], "types": {"enabled": "boolean"}},
                "set_tts_enabled": {"required": ["enabled"], "types": {"enabled": "boolean"}},
                "set_persona_style": {"required": ["style"], "enum": {"style": sorted(VALID_PERSONA_STYLES)}},
                "set_backchannel_style": {
                    "required": ["style"],
                    "enum": {"style": sorted(VALID_BACKCHANNEL_STYLES)},
                },
                "preview_personality": {
                    "required": [],
                    "enum": {
                        "persona_style": sorted(VALID_PERSONA_STYLES),
                        "backchannel_style": sorted(VALID_BACKCHANNEL_STYLES),
                    },
                },
                "commit_personality_preview": {"required": []},
                "rollback_personality_preview": {"required": []},
                "set_voice_profile": {
                    "required": ["user"],
                    "types": {"user": "string"},
                    "enum": {
                        "verbosity": sorted(VALID_VOICE_PROFILE_VERBOSITY),
                        "confirmations": sorted(VALID_VOICE_PROFILE_CONFIRMATIONS),
                        "pace": sorted(VALID_VOICE_PROFILE_PACE),
                    },
                },
                "clear_voice_profile": {"required": ["user"], "types": {"user": "string"}},
                "list_voice_profiles": {"required": []},
                "apply_control_preset": {"required": ["preset"], "enum": {"preset": sorted(VALID_CONTROL_PRESETS)}},
                "export_runtime_profile": {"required": []},
                "import_runtime_profile": {"required": ["profile"], "types": {"profile": "object"}},
                "skills_reload": {"required": []},
                "skills_enable": {"required": ["name"], "types": {"name": "string"}},
                "skills_disable": {"required": ["name"], "types": {"name": "string"}},
                "clear_inbound_webhooks": {"required": []},
            },
        }

    def _operator_available_actions(self) -> list[str]:
        schema = self._operator_control_schema()
        actions = schema.get("actions")
        if not isinstance(actions, dict):
            return []
        return sorted(str(name) for name in actions)

    def _startup_blockers(self) -> list[str]:
        blockers: list[str] = []
        if not bool(getattr(self.config, "startup_strict", False)):
            return blockers
        if not bool(getattr(self.args, "no_tts", False)) and not str(getattr(self.config, "elevenlabs_api_key", "")):
            blockers.append("STARTUP_STRICT: ELEVENLABS_API_KEY is required when TTS is enabled.")
        if bool(getattr(self.config, "operator_server_enabled", False)) and not str(
            getattr(self.config, "operator_server_host", "")
        ).strip():
            blockers.append("STARTUP_STRICT: OPERATOR_SERVER_HOST cannot be empty.")
        operator_host = str(getattr(self.config, "operator_server_host", "")).strip().lower()
        operator_auth_mode = str(getattr(self.config, "operator_auth_mode", "token")).strip().lower()
        if operator_auth_mode not in VALID_OPERATOR_AUTH_MODES:
            operator_auth_mode = "token"
        operator_token = str(getattr(self.config, "operator_auth_token", "")).strip()
        if (
            bool(getattr(self.config, "operator_server_enabled", False))
            and operator_auth_mode in {"token", "session"}
            and not operator_token
        ):
            blockers.append(
                f"STARTUP_STRICT: OPERATOR_AUTH_MODE={operator_auth_mode} requires OPERATOR_AUTH_TOKEN."
            )
        if (
            bool(getattr(self.config, "operator_server_enabled", False))
            and operator_auth_mode == "off"
            and operator_host not in {"127.0.0.1", "localhost", "::1"}
        ):
            blockers.append("STARTUP_STRICT: OPERATOR_AUTH_MODE=off is not allowed on non-loopback OPERATOR_SERVER_HOST.")
        if bool(getattr(self.config, "skills_require_signature", False)) and not str(
            getattr(self.config, "skills_signature_key", "")
        ).strip():
            blockers.append("STARTUP_STRICT: SKILLS_SIGNATURE_KEY required when SKILLS_REQUIRE_SIGNATURE=true.")
        if (
            bool(getattr(self.config, "memory_encryption_enabled", False))
            or bool(getattr(self.config, "audit_encryption_enabled", False))
        ) and not str(getattr(self.config, "data_encryption_key", "")).strip():
            blockers.append("STARTUP_STRICT: JARVIS_DATA_KEY required when encryption is enabled.")
        if bool(getattr(self.config, "webhook_inbound_enabled", False)) and not str(
            getattr(self.config, "webhook_inbound_token", "") or getattr(self.config, "webhook_auth_token", "")
        ).strip():
            blockers.append("STARTUP_STRICT: WEBHOOK_INBOUND_ENABLED requires WEBHOOK_INBOUND_TOKEN or WEBHOOK_AUTH_TOKEN.")
        return blockers

    def _load_runtime_state(self) -> None:
        path = getattr(self, "_runtime_state_path", None)
        if path is None or not isinstance(path, Path):
            return
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text())
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        voice = self._voice_controller()
        voice_state = payload.get("voice")
        if isinstance(voice_state, dict):
            if "mode" in voice_state:
                voice.set_mode(str(voice_state.get("mode", voice.mode)))
            if "timeout_profile" in voice_state:
                voice.set_timeout_profile(str(voice_state.get("timeout_profile", voice.timeout_profile)))
            voice.set_push_to_talk_active(bool(voice_state.get("push_to_talk_active", False)))
            voice.sleeping = bool(voice_state.get("sleeping", False))
        runtime_state = payload.get("runtime")
        if isinstance(runtime_state, dict):
            motion_enabled = self._parse_control_bool(runtime_state.get("motion_enabled"))
            if motion_enabled is not None:
                self.config.motion_enabled = motion_enabled
            home_enabled = self._parse_control_bool(runtime_state.get("home_enabled"))
            if home_enabled is not None:
                self.config.home_enabled = home_enabled
            safe_mode_enabled = self._parse_control_bool(runtime_state.get("safe_mode_enabled"))
            if safe_mode_enabled is not None:
                self.config.safe_mode_enabled = safe_mode_enabled
            tts_enabled = self._parse_control_bool(runtime_state.get("tts_enabled"))
            if tts_enabled is not None:
                self._tts_output_enabled = tts_enabled
            persona_style = self._parse_control_choice(runtime_state.get("persona_style"), VALID_PERSONA_STYLES)
            if persona_style is not None:
                self._set_persona_style(persona_style)
            backchannel_style = self._parse_control_choice(
                runtime_state.get("backchannel_style"), VALID_BACKCHANNEL_STYLES
            )
            if backchannel_style is not None:
                self.config.backchannel_style = backchannel_style
                self.presence.set_backchannel_style(backchannel_style)
            raw_profiles = runtime_state.get("voice_user_profiles")
            if isinstance(raw_profiles, dict):
                parsed_profiles: dict[str, dict[str, str]] = {}
                for raw_user, raw_profile in raw_profiles.items():
                    user = str(raw_user).strip().lower()
                    if not user or not isinstance(raw_profile, dict):
                        continue
                    profile: dict[str, str] = {}
                    verbosity = self._parse_control_choice(raw_profile.get("verbosity"), VALID_VOICE_PROFILE_VERBOSITY)
                    confirmations = self._parse_control_choice(
                        raw_profile.get("confirmations"),
                        VALID_VOICE_PROFILE_CONFIRMATIONS,
                    )
                    pace = self._parse_control_choice(raw_profile.get("pace"), VALID_VOICE_PROFILE_PACE)
                    if verbosity is not None:
                        profile["verbosity"] = verbosity
                    if confirmations is not None:
                        profile["confirmations"] = confirmations
                    if pace is not None:
                        profile["pace"] = pace
                    if profile:
                        parsed_profiles[user] = profile
                self._voice_user_profiles = parsed_profiles
            preset = str(runtime_state.get("active_control_preset", "custom")).strip().lower()
            self._active_control_preset = preset if preset in VALID_CONTROL_PRESETS else "custom"
        service_tools.set_safe_mode(bool(getattr(self.config, "safe_mode_enabled", False)))
        self._awaiting_confirmation = bool(payload.get("awaiting_confirmation", False))
        pending = payload.get("pending_text")
        self._pending_text = str(pending) if isinstance(pending, str) else None
        self._awaiting_repair_confirmation = bool(payload.get("awaiting_repair_confirmation", False))
        repair_pending = payload.get("repair_candidate_text")
        self._repair_candidate_text = str(repair_pending) if isinstance(repair_pending, str) else None
        if not self._awaiting_repair_confirmation:
            self._repair_candidate_text = None
        elif not self._repair_candidate_text:
            self._awaiting_repair_confirmation = False
        raw_timeline = payload.get("episodic_timeline")
        parsed_timeline: list[dict[str, Any]] = []

        def safe_int(value: Any, default: int = 0) -> int:
            try:
                number = int(value)
            except (TypeError, ValueError):
                return default
            return number

        def safe_float(value: Any, default: float = 0.0) -> float:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(number):
                return default
            return number

        if isinstance(raw_timeline, list):
            for item in raw_timeline[:EPISODIC_TIMELINE_MAXLEN]:
                if not isinstance(item, dict):
                    continue
                snapshot = {
                    "episode_id": safe_int(item.get("episode_id", 0), 0),
                    "timestamp": safe_float(item.get("timestamp", 0.0), 0.0),
                    "turn_id": safe_int(item.get("turn_id", 0), 0),
                    "intent": str(item.get("intent", "unknown")),
                    "lifecycle": str(item.get("lifecycle", "unknown")),
                    "summary": str(item.get("summary", "")).strip()[:240],
                    "tool_count": max(0, safe_int(item.get("tool_count", 0), 0)),
                    "completion_success": item.get("completion_success"),
                    "response_success": item.get("response_success"),
                }
                if snapshot["episode_id"] <= 0 or snapshot["timestamp"] <= 0.0 or not snapshot["summary"]:
                    continue
                parsed_timeline.append(snapshot)
        self._episodic_timeline = deque(parsed_timeline, maxlen=EPISODIC_TIMELINE_MAXLEN)
        try:
            loaded_episode_seq = int(payload.get("episodic_timeline_seq", 0) or 0)
        except (TypeError, ValueError):
            loaded_episode_seq = 0
        self._episode_seq = max(loaded_episode_seq, len(parsed_timeline))

    def _save_runtime_state(self) -> None:
        path = getattr(self, "_runtime_state_path", None)
        if path is None or not isinstance(path, Path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        voice = self._voice_controller()
        preview_snapshot = getattr(self, "_personality_preview_snapshot", None)
        if isinstance(preview_snapshot, dict):
            persisted_persona_style = self._parse_control_choice(
                preview_snapshot.get("persona_style"),
                VALID_PERSONA_STYLES,
            ) or str(getattr(self.config, "persona_style", "composed"))
            persisted_backchannel_style = self._parse_control_choice(
                preview_snapshot.get("backchannel_style"),
                VALID_BACKCHANNEL_STYLES,
            ) or str(getattr(self.config, "backchannel_style", "balanced"))
        else:
            persisted_persona_style = str(getattr(self.config, "persona_style", "composed"))
            persisted_backchannel_style = str(getattr(self.config, "backchannel_style", "balanced"))
        payload = {
            "saved_at": time.time(),
            "voice": {
                "mode": voice.mode,
                "timeout_profile": voice.timeout_profile,
                "push_to_talk_active": voice.push_to_talk_active,
                "sleeping": voice.sleeping,
            },
            "runtime": {
                "motion_enabled": bool(self.config.motion_enabled),
                "home_enabled": bool(self.config.home_enabled),
                "safe_mode_enabled": bool(getattr(self.config, "safe_mode_enabled", False)),
                "tts_enabled": bool(getattr(self, "_tts_output_enabled", True)),
                "persona_style": persisted_persona_style,
                "backchannel_style": persisted_backchannel_style,
                "voice_user_profiles": getattr(self, "_voice_user_profiles", {}),
                "active_control_preset": str(getattr(self, "_active_control_preset", "custom")),
            },
            "awaiting_confirmation": bool(getattr(self, "_awaiting_confirmation", False)),
            "pending_text": getattr(self, "_pending_text", None),
            "awaiting_repair_confirmation": bool(getattr(self, "_awaiting_repair_confirmation", False)),
            "repair_candidate_text": getattr(self, "_repair_candidate_text", None),
            "episodic_timeline_seq": int(getattr(self, "_episode_seq", 0)),
            "episodic_timeline": list(getattr(self, "_episodic_timeline", []))[:EPISODIC_TIMELINE_MAXLEN],
        }
        with suppress(OSError):
            path.write_text(json.dumps(payload, indent=2))

    def _voice_controller(self) -> VoiceAttentionController:
        voice = getattr(self, "_voice_attention", None)
        if voice is not None:
            return voice
        fallback = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
        self._voice_attention = fallback
        return fallback

    def _active_voice_user(self) -> str:
        config = getattr(self, "config", None)
        user = str(getattr(config, "identity_default_user", "operator")).strip().lower()
        return user or "operator"

    def _active_voice_profile(self, *, user: str | None = None) -> dict[str, str]:
        profile = {
            "verbosity": "normal",
            "confirmations": "standard",
            "pace": "normal",
        }
        key = str(user or self._active_voice_user()).strip().lower()
        profiles = getattr(self, "_voice_user_profiles", None)
        if isinstance(profiles, dict):
            raw = profiles.get(key)
            if isinstance(raw, dict):
                verbosity = self._parse_control_choice(raw.get("verbosity"), VALID_VOICE_PROFILE_VERBOSITY)
                confirmations = self._parse_control_choice(raw.get("confirmations"), VALID_VOICE_PROFILE_CONFIRMATIONS)
                pace = self._parse_control_choice(raw.get("pace"), VALID_VOICE_PROFILE_PACE)
                if verbosity is not None:
                    profile["verbosity"] = verbosity
                if confirmations is not None:
                    profile["confirmations"] = confirmations
                if pace is not None:
                    profile["pace"] = pace
        return profile

    def _with_voice_profile_guidance(self, text: str) -> str:
        profile = self._active_voice_profile()
        verbosity = profile.get("verbosity", "normal")
        if verbosity == "brief":
            guidance = "User voice preference: keep responses concise unless safety requires detail."
        elif verbosity == "detailed":
            guidance = "User voice preference: provide fuller detail and explicit steps."
        else:
            return text
        return f"{text}\n\nVoice profile preference:\n{guidance}"

    def _runtime_invariant_snapshot(self) -> dict[str, Any]:
        recent = list(getattr(self, "_runtime_invariant_recent", []))
        return {
            "last_checked_at": float(getattr(self, "_runtime_invariant_checked_at", 0.0)),
            "total_violations": int(getattr(self, "_runtime_invariant_violations_total", 0)),
            "total_auto_heals": int(getattr(self, "_runtime_invariant_auto_heals_total", 0)),
            "recent": recent[:20],
        }

    def _check_runtime_invariants(self, *, auto_heal: bool = True) -> dict[str, Any]:
        now = time.time()
        self._runtime_invariant_checked_at = now
        self._runtime_invariant_checked_monotonic = time.monotonic()
        voice = self._voice_controller()
        violations: list[dict[str, Any]] = []
        mode = str(getattr(voice, "mode", "unknown")).strip().lower()
        push_to_talk_active = bool(getattr(voice, "push_to_talk_active", False))

        if mode == "push_to_talk" and not push_to_talk_active:
            healed = False
            if auto_heal:
                voice.set_push_to_talk_active(True)
                healed = True
            violations.append(
                {
                    "code": "push_to_talk_mode_inactive",
                    "message": "wake mode push_to_talk requires push_to_talk_active=true",
                    "healed": healed,
                }
            )
        if mode != "push_to_talk" and push_to_talk_active:
            healed = False
            if auto_heal:
                voice.set_push_to_talk_active(False)
                healed = True
            violations.append(
                {
                    "code": "push_to_talk_active_mode_mismatch",
                    "message": "push_to_talk_active=true requires wake mode push_to_talk",
                    "healed": healed,
                }
            )

        preset = str(getattr(self, "_active_control_preset", "custom")).strip().lower()
        if preset not in VALID_CONTROL_PRESETS and preset != "custom":
            healed = False
            if auto_heal:
                self._active_control_preset = "custom"
                healed = True
            violations.append(
                {
                    "code": "invalid_control_preset",
                    "message": "active control preset must be known or custom",
                    "healed": healed,
                }
            )

        recent = getattr(self, "_runtime_invariant_recent", None)
        if not isinstance(recent, deque):
            recent = deque(maxlen=RUNTIME_INVARIANT_HISTORY_MAXLEN)
            self._runtime_invariant_recent = recent
        if not hasattr(self, "_runtime_invariant_violations_total"):
            self._runtime_invariant_violations_total = 0
        if not hasattr(self, "_runtime_invariant_auto_heals_total"):
            self._runtime_invariant_auto_heals_total = 0

        healed_any = False
        for item in violations:
            healed = bool(item.get("healed", False))
            if healed:
                healed_any = True
            self._runtime_invariant_violations_total += 1
            if healed:
                self._runtime_invariant_auto_heals_total += 1
            record = {
                "timestamp": now,
                "code": str(item.get("code", "unknown")),
                "message": str(item.get("message", "")),
                "healed": healed,
            }
            recent.appendleft(record)
            observability = getattr(self, "_observability", None)
            if observability is not None:
                with suppress(Exception):
                    observability.record_event("runtime_invariant", record)

        if healed_any:
            self._persist_runtime_state_safe()

        return self._runtime_invariant_snapshot()

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        if q <= 0.0:
            return float(values[0])
        if q >= 1.0:
            return float(values[-1])
        idx = (len(values) - 1) * q
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return float(values[lo])
        frac = idx - lo
        return float(values[lo] + ((values[hi] - values[lo]) * frac))

    def _conversation_latency_analytics(self) -> dict[str, Any]:
        traces = list(getattr(self, "_conversation_traces", []))
        if not traces:
            return {
                "sample_count": 0,
                "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                "by_intent": {},
                "by_tool_mix": {},
                "by_wake_mode": {},
            }

        def extract_total(item: dict[str, Any]) -> float:
            if not isinstance(item, dict):
                return 0.0
            latencies = item.get("latencies_ms")
            if not isinstance(latencies, dict):
                return 0.0
            try:
                value = float(latencies.get("total", 0.0))
            except (TypeError, ValueError):
                return 0.0
            if not math.isfinite(value) or value < 0.0:
                return 0.0
            return value

        def pack(values: list[float]) -> dict[str, float]:
            ordered = sorted(v for v in values if math.isfinite(v) and v >= 0.0)
            return {
                "p50": self._percentile(ordered, 0.5),
                "p95": self._percentile(ordered, 0.95),
                "p99": self._percentile(ordered, 0.99),
            }

        overall_values = [extract_total(item) for item in traces]
        by_intent: dict[str, list[float]] = {}
        by_tool_mix: dict[str, list[float]] = {}
        by_wake_mode: dict[str, list[float]] = {}
        for item in traces:
            if not isinstance(item, dict):
                continue
            total = extract_total(item)
            intent = str(item.get("intent", "unknown")).strip().lower() or "unknown"
            by_intent.setdefault(intent, []).append(total)
            tools = item.get("tool_calls")
            tool_count = len(tools) if isinstance(tools, list) else 0
            if tool_count <= 0:
                tool_mix = "none"
            elif tool_count == 1:
                tool_mix = "single"
            else:
                tool_mix = "multi"
            by_tool_mix.setdefault(tool_mix, []).append(total)
            wake_mode = str(item.get("wake_mode", "unknown")).strip().lower() or "unknown"
            by_wake_mode.setdefault(wake_mode, []).append(total)

        return {
            "sample_count": len(overall_values),
            "overall_total_ms": pack(overall_values),
            "by_intent": {name: pack(values) for name, values in sorted(by_intent.items())},
            "by_tool_mix": {name: pack(values) for name, values in sorted(by_tool_mix.items())},
            "by_wake_mode": {name: pack(values) for name, values in sorted(by_wake_mode.items())},
        }

    def _policy_decision_analytics(self) -> dict[str, Any]:
        traces = list(getattr(self, "_conversation_traces", []))
        totals_by_tool: dict[str, int] = {}
        totals_by_reason: dict[str, int] = {}
        totals_by_status: dict[str, int] = {}
        totals_by_user: dict[str, int] = {}
        by_user_tool: dict[str, dict[str, int]] = {}
        total_decisions = 0
        for item in traces:
            if not isinstance(item, dict):
                continue
            requester = str(item.get("requester_user", "unknown")).strip().lower() or "unknown"
            decisions = item.get("policy_decisions")
            if not isinstance(decisions, list):
                continue
            for decision in decisions:
                if not isinstance(decision, dict):
                    continue
                total_decisions += 1
                tool = str(decision.get("tool", "unknown")).strip().lower() or "unknown"
                status = str(decision.get("status", "unknown")).strip().lower() or "unknown"
                reason = str(decision.get("detail", "unknown")).strip().lower() or "unknown"
                totals_by_tool[tool] = totals_by_tool.get(tool, 0) + 1
                totals_by_status[status] = totals_by_status.get(status, 0) + 1
                totals_by_reason[reason] = totals_by_reason.get(reason, 0) + 1
                totals_by_user[requester] = totals_by_user.get(requester, 0) + 1
                if requester not in by_user_tool:
                    by_user_tool[requester] = {}
                user_tool = by_user_tool[requester]
                user_tool[tool] = user_tool.get(tool, 0) + 1

        return {
            "decision_count": total_decisions,
            "by_tool": {name: totals_by_tool[name] for name in sorted(totals_by_tool)},
            "by_status": {name: totals_by_status[name] for name in sorted(totals_by_status)},
            "by_reason": {name: totals_by_reason[name] for name in sorted(totals_by_reason)},
            "by_user": {name: totals_by_user[name] for name in sorted(totals_by_user)},
            "by_user_tool": {
                user: {tool: by_user_tool[user][tool] for tool in sorted(by_user_tool[user])}
                for user in sorted(by_user_tool)
            },
        }

    def _runtime_profile_snapshot(self) -> dict[str, Any]:
        voice = self._voice_controller()
        return {
            "wake_mode": str(getattr(voice, "mode", "wake_word")),
            "sleeping": bool(getattr(voice, "sleeping", False)),
            "timeout_profile": str(getattr(voice, "timeout_profile", "normal")),
            "push_to_talk_active": bool(getattr(voice, "push_to_talk_active", False)),
            "motion_enabled": bool(getattr(self.config, "motion_enabled", False)),
            "home_enabled": bool(getattr(self.config, "home_enabled", False)),
            "safe_mode_enabled": bool(getattr(self.config, "safe_mode_enabled", False)),
            "tts_enabled": bool(getattr(self, "_tts_output_enabled", True)),
            "persona_style": str(getattr(self.config, "persona_style", "composed")),
            "backchannel_style": str(getattr(self.config, "backchannel_style", "balanced")),
            "voice_user_profiles": {
                str(name): dict(profile)
                for name, profile in getattr(self, "_voice_user_profiles", {}).items()
                if isinstance(profile, dict)
            },
            "active_control_preset": str(getattr(self, "_active_control_preset", "custom")),
        }

    def _apply_runtime_profile(self, profile: dict[str, Any], *, mark_custom: bool = True) -> dict[str, Any]:
        voice = self._voice_controller()
        wake_mode = self._parse_control_choice(profile.get("wake_mode"), VALID_WAKE_MODES)
        if wake_mode is not None:
            voice.set_mode(wake_mode)
        sleeping = self._parse_control_bool(profile.get("sleeping"))
        if sleeping is not None:
            voice.sleeping = sleeping
            if not sleeping:
                voice.continue_listening()
        timeout_profile = self._parse_control_choice(profile.get("timeout_profile"), VALID_TIMEOUT_PROFILES)
        if timeout_profile is not None:
            voice.set_timeout_profile(timeout_profile)
        push_to_talk = self._parse_control_bool(profile.get("push_to_talk_active"))
        if push_to_talk is not None:
            voice.set_push_to_talk_active(push_to_talk)

        motion_enabled = self._parse_control_bool(profile.get("motion_enabled"))
        if motion_enabled is not None:
            self.config.motion_enabled = motion_enabled
            if motion_enabled:
                with suppress(Exception):
                    self.presence.start()
            else:
                with suppress(Exception):
                    self.presence.stop()
        home_enabled = self._parse_control_bool(profile.get("home_enabled"))
        if home_enabled is not None:
            self.config.home_enabled = home_enabled
        safe_mode_enabled = self._parse_control_bool(profile.get("safe_mode_enabled"))
        if safe_mode_enabled is not None:
            self.config.safe_mode_enabled = safe_mode_enabled
            service_tools.set_safe_mode(safe_mode_enabled)
        tts_enabled = self._parse_control_bool(profile.get("tts_enabled"))
        if tts_enabled is not None:
            self._tts_output_enabled = tts_enabled

        persona_style = self._parse_control_choice(profile.get("persona_style"), VALID_PERSONA_STYLES)
        if persona_style is not None:
            self._set_persona_style(persona_style)
        backchannel_style = self._parse_control_choice(profile.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
        if backchannel_style is not None:
            self.config.backchannel_style = backchannel_style
            self.presence.set_backchannel_style(backchannel_style)

        raw_profiles = profile.get("voice_user_profiles")
        if isinstance(raw_profiles, dict):
            parsed_profiles: dict[str, dict[str, str]] = {}
            for raw_user, raw_profile in raw_profiles.items():
                user = str(raw_user).strip().lower()
                if not user or not isinstance(raw_profile, dict):
                    continue
                parsed: dict[str, str] = {}
                verbosity = self._parse_control_choice(raw_profile.get("verbosity"), VALID_VOICE_PROFILE_VERBOSITY)
                confirmations = self._parse_control_choice(raw_profile.get("confirmations"), VALID_VOICE_PROFILE_CONFIRMATIONS)
                pace = self._parse_control_choice(raw_profile.get("pace"), VALID_VOICE_PROFILE_PACE)
                if verbosity is not None:
                    parsed["verbosity"] = verbosity
                if confirmations is not None:
                    parsed["confirmations"] = confirmations
                if pace is not None:
                    parsed["pace"] = pace
                if parsed:
                    parsed_profiles[user] = parsed
            self._voice_user_profiles = parsed_profiles

        if mark_custom:
            self._active_control_preset = "custom"
        self._publish_voice_status()
        self._persist_runtime_state_safe()
        return self._runtime_profile_snapshot()

    def _preset_profile(self, preset: str) -> dict[str, Any]:
        name = str(preset or "").strip().lower()
        if name == "quiet_hours":
            return {
                "wake_mode": "wake_word",
                "sleeping": False,
                "timeout_profile": "short",
                "push_to_talk_active": False,
                "motion_enabled": bool(getattr(self.config, "motion_enabled", False)),
                "home_enabled": False,
                "safe_mode_enabled": True,
                "tts_enabled": True,
                "persona_style": "composed",
                "backchannel_style": "quiet",
            }
        if name == "demo_mode":
            return {
                "wake_mode": "always_listening",
                "sleeping": False,
                "timeout_profile": "long",
                "push_to_talk_active": False,
                "motion_enabled": True,
                "home_enabled": False,
                "safe_mode_enabled": True,
                "tts_enabled": True,
                "persona_style": "friendly",
                "backchannel_style": "expressive",
            }
        if name == "maintenance_mode":
            return {
                "wake_mode": "push_to_talk",
                "sleeping": True,
                "timeout_profile": "short",
                "push_to_talk_active": True,
                "motion_enabled": False,
                "home_enabled": False,
                "safe_mode_enabled": True,
                "tts_enabled": False,
                "persona_style": "terse",
                "backchannel_style": "quiet",
            }
        return {}

    def _apply_control_preset(self, preset: str) -> dict[str, Any] | None:
        name = str(preset or "").strip().lower()
        if name not in VALID_CONTROL_PRESETS:
            return None
        profile = self._preset_profile(name)
        applied = self._apply_runtime_profile(profile, mark_custom=False)
        self._active_control_preset = name
        self._publish_voice_status()
        self._persist_runtime_state_safe()
        return applied

    def _refresh_tool_error_counters(self) -> None:
        try:
            recent = list_summaries(limit=200)
        except Exception:
            return
        service_errors = 0
        storage_errors = 0
        unknown_summary_details = 0
        per_code: dict[str, float] = {}
        for item in recent:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", ""))
            detail = str(item.get("detail", ""))
            if status != "error":
                continue
            if detail in TOOL_SERVICE_ERROR_CODES:
                per_code[detail] = per_code.get(detail, 0.0) + 1.0
            if detail in TELEMETRY_STORAGE_ERROR_DETAILS:
                storage_errors += 1
                continue
            if detail in TELEMETRY_SERVICE_ERROR_DETAILS:
                service_errors += 1
                continue
            unknown_summary_details += 1
        self._telemetry["service_errors"] = float(service_errors)
        self._telemetry["storage_errors"] = float(storage_errors)
        self._telemetry["unknown_summary_details"] = float(unknown_summary_details)
        self._telemetry_error_counts = {name: per_code[name] for name in sorted(per_code)}

    def _telemetry_snapshot(self) -> dict[str, Any]:
        def metric(key: str) -> float:
            value = self._telemetry.get(key, 0.0)
            if not math.isfinite(value):
                return 0.0
            return value

        def avg(total_key: str, count_key: str) -> float:
            count = metric(count_key)
            if count <= 0.0:
                return 0.0
            total = metric(total_key)
            value = total / count
            if not math.isfinite(value):
                return 0.0
            return value

        counts = {
            name: value
            for name, value in getattr(self, "_telemetry_error_counts", {}).items()
            if math.isfinite(value)
        }
        intent_turns = metric("intent_turns_total")
        answer_total = metric("intent_answer_total")
        completion_total = metric("intent_completion_total")
        answer_success_rate = (metric("intent_answer_success") / answer_total) if answer_total > 0.0 else 0.0
        completion_success_rate = (
            (metric("intent_completion_success") / completion_total) if completion_total > 0.0 else 0.0
        )
        correction_frequency = (metric("intent_corrections") / intent_turns) if intent_turns > 0.0 else 0.0
        return {
            "turns": metric("turns"),
            "barge_ins": metric("barge_ins"),
            "avg_stt_latency_ms": avg("stt_latency_total_ms", "stt_latency_count"),
            "avg_llm_first_sentence_ms": avg("llm_first_sentence_total_ms", "llm_first_sentence_count"),
            "avg_tts_first_audio_ms": avg("tts_first_audio_total_ms", "tts_first_audio_count"),
            "service_errors": metric("service_errors"),
            "storage_errors": metric("storage_errors"),
            "unknown_summary_details": metric("unknown_summary_details"),
            "service_error_counts": counts,
            "fallback_responses": metric("fallback_responses"),
            "intent_metrics": {
                "turn_count": intent_turns,
                "answer_intent_count": metric("intent_answer_turns"),
                "action_intent_count": metric("intent_action_turns"),
                "hybrid_intent_count": metric("intent_hybrid_turns"),
                "answer_sample_count": answer_total,
                "completion_sample_count": completion_total,
                "answer_quality_success_rate": answer_success_rate,
                "completion_success_rate": completion_success_rate,
                "correction_count": metric("intent_corrections"),
                "correction_frequency": correction_frequency,
            },
        }

    @staticmethod
    def _default_stt_diagnostics() -> dict[str, Any]:
        return {
            "source": "none",
            "fallback_used": False,
            "confidence_score": 0.0,
            "confidence_band": "unknown",
            "avg_logprob": -3.0,
            "avg_no_speech_prob": 1.0,
            "language": "unknown",
            "language_probability": 0.0,
            "segment_count": 0,
            "word_count": 0,
            "char_count": 0,
            "updated_at": 0.0,
            "error": "",
        }

    @staticmethod
    def _stt_confidence_band(score: float, *, has_words: bool) -> str:
        if not has_words:
            return "unknown"
        if score >= 0.78:
            return "high"
        if score >= 0.50:
            return "medium"
        return "low"

    def _stt_diagnostics_snapshot(self) -> dict[str, Any]:
        snapshot = self._default_stt_diagnostics()
        current = getattr(self, "_stt_diagnostics", None)
        if isinstance(current, dict):
            for key in snapshot:
                if key in current:
                    snapshot[key] = current[key]

        def safe_float(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(number):
                return default
            if minimum is not None:
                number = max(minimum, number)
            if maximum is not None:
                number = min(maximum, number)
            return number

        def safe_int(value: Any, default: int = 0) -> int:
            try:
                number = int(value)
            except (TypeError, ValueError):
                return default
            return max(0, number)

        snapshot["source"] = str(snapshot.get("source", "none")).strip().lower() or "none"
        snapshot["fallback_used"] = bool(snapshot.get("fallback_used", False))
        snapshot["confidence_score"] = safe_float(snapshot.get("confidence_score"), 0.0, minimum=0.0, maximum=1.0)
        band = str(snapshot.get("confidence_band", "unknown")).strip().lower()
        if band not in {"unknown", "low", "medium", "high"}:
            band = self._stt_confidence_band(
                float(snapshot["confidence_score"]),
                has_words=safe_int(snapshot.get("word_count")) > 0,
            )
        snapshot["confidence_band"] = band
        snapshot["avg_logprob"] = safe_float(snapshot.get("avg_logprob"), -3.0)
        snapshot["avg_no_speech_prob"] = safe_float(
            snapshot.get("avg_no_speech_prob"),
            1.0,
            minimum=0.0,
            maximum=1.0,
        )
        snapshot["language"] = str(snapshot.get("language", "unknown")).strip().lower() or "unknown"
        snapshot["language_probability"] = safe_float(
            snapshot.get("language_probability"),
            0.0,
            minimum=0.0,
            maximum=1.0,
        )
        snapshot["segment_count"] = safe_int(snapshot.get("segment_count"))
        snapshot["word_count"] = safe_int(snapshot.get("word_count"))
        snapshot["char_count"] = safe_int(snapshot.get("char_count"))
        snapshot["updated_at"] = safe_float(snapshot.get("updated_at"), 0.0, minimum=0.0)
        snapshot["error"] = str(snapshot.get("error", "")).strip().lower()
        return snapshot

    @staticmethod
    def _transcribe_with_optional_diagnostics(model: Any, audio: np.ndarray) -> tuple[str, dict[str, Any]]:
        diagnostics_method = getattr(model, "transcribe_with_diagnostics", None)
        if callable(diagnostics_method):
            with suppress(Exception):
                result = diagnostics_method(audio)
                if isinstance(result, tuple) and len(result) == 2:
                    text = str(result[0] or "")
                    diagnostics = result[1]
                    if isinstance(diagnostics, dict):
                        return text, {str(key): value for key, value in diagnostics.items()}
                    return text, {}
        text = model.transcribe(audio)
        return str(text or ""), {}

    def _update_stt_diagnostics(
        self,
        *,
        text: str,
        source: str,
        fallback_used: bool,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        payload = self._default_stt_diagnostics()
        diag = diagnostics if isinstance(diagnostics, dict) else {}

        def safe_float(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(number):
                return default
            if minimum is not None:
                number = max(minimum, number)
            if maximum is not None:
                number = min(maximum, number)
            return number

        def safe_int(value: Any, default: int = 0) -> int:
            try:
                number = int(value)
            except (TypeError, ValueError):
                return default
            return max(0, number)

        transcript = str(text or "").strip()
        words = re.findall(r"[a-z0-9']+", transcript.lower())
        word_count = len(words)
        char_count = len(transcript)
        confidence_score_raw = diag.get("confidence_score")
        confidence_score = safe_float(confidence_score_raw, -1.0, minimum=-1.0, maximum=1.0)
        if confidence_score < 0.0:
            confidence_score = 0.0
        if confidence_score_raw is None and transcript:
            confidence_score = min(1.0, 0.45 + min(0.4, word_count / 20.0))
        confidence_band = str(diag.get("confidence_band", "")).strip().lower()
        if confidence_band not in {"unknown", "low", "medium", "high"}:
            confidence_band = self._stt_confidence_band(confidence_score, has_words=word_count > 0)

        payload.update(
            {
                "source": str(source or "none").strip().lower() or "none",
                "fallback_used": bool(fallback_used),
                "confidence_score": confidence_score,
                "confidence_band": confidence_band,
                "avg_logprob": safe_float(diag.get("avg_logprob"), -3.0),
                "avg_no_speech_prob": safe_float(diag.get("avg_no_speech_prob"), 1.0, minimum=0.0, maximum=1.0),
                "language": str(diag.get("language", "unknown")).strip().lower() or "unknown",
                "language_probability": safe_float(diag.get("language_probability"), 0.0, minimum=0.0, maximum=1.0),
                "segment_count": safe_int(diag.get("segment_count", 0)),
                "word_count": word_count if word_count else safe_int(diag.get("word_count", 0)),
                "char_count": char_count if char_count else safe_int(diag.get("char_count", 0)),
                "updated_at": time.time(),
                "error": str(diag.get("error", "")).strip().lower(),
            }
        )
        self._stt_diagnostics = payload

    def _transcribe_with_fallback(self, audio: np.ndarray) -> str:
        text, primary_diag = self._transcribe_with_optional_diagnostics(self.stt, audio)
        self._update_stt_diagnostics(
            text=text,
            source="primary",
            fallback_used=False,
            diagnostics=primary_diag,
        )
        if text.strip():
            return text
        fallback = getattr(self, "_stt_secondary", None)
        if fallback is None:
            return text
        recovered, fallback_diag = self._transcribe_with_optional_diagnostics(fallback, audio)
        self._update_stt_diagnostics(
            text=recovered,
            source="secondary",
            fallback_used=bool(recovered.strip()),
            diagnostics=fallback_diag,
        )
        if recovered.strip():
            self._telemetry["fallback_responses"] += 1.0
            observability = getattr(self, "_observability", None)
            if observability is not None:
                with suppress(Exception):
                    observability.record_event("stt_fallback", {"reason": "primary_empty"})
        return recovered

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
        try:
            payload = await service_tools.system_status({})
            text = payload.get("content", [{}])[0].get("text", "{}")
            status = json.loads(text) if isinstance(text, str) else {}
            if not isinstance(status, dict):
                status = {}
        except Exception as exc:
            status = {"error": str(exc)}
        latest = self._operator_conversation_trace_provider(limit=1)
        latest_turn_id = int(latest[0].get("turn_id", 0)) if latest and isinstance(latest[0], dict) else 0
        status["operator"] = {
            "enabled": bool(self.config.operator_server_enabled),
            "host": self.config.operator_server_host,
            "port": int(self.config.operator_server_port),
            "auth_mode": str(getattr(self.config, "operator_auth_mode", "token")).strip().lower(),
            "auth_required": str(getattr(self.config, "operator_auth_mode", "token")).strip().lower() != "off",
            "auth_token_configured": bool(str(getattr(self.config, "operator_auth_token", "")).strip()),
        }
        mode = status["operator"]["auth_mode"]
        if mode not in VALID_OPERATOR_AUTH_MODES:
            mode = "token"
            status["operator"]["auth_mode"] = mode
        token_set = bool(status["operator"]["auth_token_configured"])
        if mode == "off":
            status["operator"]["auth_risk"] = "high"
        elif not token_set:
            status["operator"]["auth_risk"] = "high"
        elif mode == "session":
            status["operator"]["auth_risk"] = "low"
        else:
            status["operator"]["auth_risk"] = "medium"
        status["conversation_trace"] = {
            "recent_count": len(self._conversation_traces),
            "latest_turn_id": latest_turn_id,
        }
        episodes = self._operator_episodic_timeline_provider(limit=20)
        latest_episode_id = int(episodes[0].get("episode_id", 0)) if episodes and isinstance(episodes[0], dict) else 0
        status["episodic_timeline"] = {
            "recent_count": len(getattr(self, "_episodic_timeline", [])),
            "latest_episode_id": latest_episode_id,
            "recent": episodes,
        }
        preview = getattr(self, "_personality_preview_snapshot", None)
        status["personality_preview"] = {
            "active": isinstance(preview, dict),
            "baseline": dict(preview) if isinstance(preview, dict) else None,
            "current": {
                "persona_style": str(getattr(self.config, "persona_style", "unknown")),
                "backchannel_style": str(getattr(self.config, "backchannel_style", "unknown")),
            },
        }
        status["operator_controls"] = {
            "active_control_preset": str(getattr(self, "_active_control_preset", "custom")),
            "available_control_presets": sorted(VALID_CONTROL_PRESETS),
            "runtime_profile": self._runtime_profile_snapshot(),
        }
        status["runtime_invariants"] = self._runtime_invariant_snapshot()
        return status

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

    @staticmethod
    def _parse_control_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return None

    @staticmethod
    def _parse_control_choice(value: Any, allowed: set[str]) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if normalized in allowed:
            return normalized
        return None

    @staticmethod
    def _parse_memory_correction_command(text: str) -> tuple[str, dict[str, Any]] | None:
        phrase = str(text or "").strip()
        if not phrase:
            return None
        forget_match = MEMORY_FORGET_RE.fullmatch(phrase)
        if forget_match:
            memory_id = int(forget_match.group("memory_id"))
            return "memory_forget", {"memory_id": memory_id}
        update_match = MEMORY_UPDATE_RE.fullmatch(phrase)
        if update_match:
            memory_id = int(update_match.group("memory_id"))
            updated_text = update_match.group("text").strip()
            if not updated_text:
                return None
            return "memory_update", {"memory_id": memory_id, "text": updated_text}
        return None

    @staticmethod
    def _classify_user_intent(text: str) -> str:
        phrase = str(text or "").strip().lower()
        if not phrase:
            return "answer"
        tokens = set(re.findall(r"[a-z']+", phrase))
        has_action = bool(tokens & ACTION_INTENT_TERMS)
        starts_with_question = any(phrase.startswith(f"{term} ") for term in QUESTION_START_TERMS)
        has_question = phrase.endswith("?") or starts_with_question
        if has_action and has_question:
            return "hybrid"
        if has_action:
            return "action"
        return "answer"

    @staticmethod
    def _looks_like_user_correction(text: str) -> bool:
        phrase = str(text or "").strip().lower()
        if not phrase:
            return False
        if any(term in phrase for term in CORRECTION_TERMS):
            return True
        return bool(re.search(r"\b(?:no|nope|nah)\b.+\b(?:meant|wanted|said)\b", phrase))

    def _is_followup_carryover_candidate(self, text: str, *, now_ts: float | None = None) -> bool:
        phrase = str(text or "").strip().lower()
        if not phrase:
            return False
        context = getattr(self, "_followup_carryover", {})
        if not isinstance(context, dict):
            return False
        previous_text = str(context.get("text", "")).strip()
        previous_intent = str(context.get("intent", "")).strip().lower()
        unresolved = bool(context.get("unresolved", False))
        try:
            previous_ts = float(context.get("timestamp", 0.0))
        except (TypeError, ValueError):
            previous_ts = 0.0
        if not math.isfinite(previous_ts) or previous_ts < 0.0:
            previous_ts = 0.0
        if not previous_text or previous_intent not in {"action", "hybrid"}:
            return False
        if now_ts is None:
            now_value = time.time()
        else:
            try:
                now_value = float(now_ts)
            except (TypeError, ValueError):
                now_value = time.time()
        if not math.isfinite(now_value):
            now_value = time.time()
        if (now_value - previous_ts) > FOLLOWUP_CARRYOVER_MAX_AGE_SEC:
            return False
        if len(phrase) > 220:
            return False
        if any(phrase.startswith(prefix) for prefix in FOLLOWUP_CARRYOVER_PREFIX_TERMS):
            return True
        word_list = [token for token in re.findall(r"[a-z0-9']+", phrase)]
        words = set(word_list)
        if words & FOLLOWUP_CARRYOVER_REFERENCE_TERMS:
            return True
        if not unresolved:
            return False
        if phrase.endswith("?"):
            return False
        if not word_list or len(word_list) > FOLLOWUP_CARRYOVER_SHORT_REPLY_MAX_WORDS:
            return False
        if words.issubset(FOLLOWUP_CARRYOVER_ACK_TERMS):
            return False
        if words & ACTION_INTENT_TERMS:
            return False
        if word_list[0] in QUESTION_START_TERMS:
            return False
        return True

    def _with_followup_carryover(self, text: str, *, now_ts: float | None = None) -> tuple[str, bool]:
        if not self._is_followup_carryover_candidate(text, now_ts=now_ts):
            return text, False
        context = getattr(self, "_followup_carryover", {})
        previous_text = str(context.get("text", "")).strip()[:220]
        unresolved = bool(context.get("unresolved", False))
        policy = (
            "Previous request may still have unresolved slots; preserve target/entity context unless user overrides."
            if unresolved
            else "Preserve prior action context unless the user explicitly overrides target or scope."
        )
        augmented = (
            f"{text}\n\nFollow-up intent carryover:\n"
            f"Previous request: {previous_text}\n"
            f"{policy}"
        )
        return augmented, True

    def _update_followup_carryover(
        self,
        text: str,
        intent_class: str,
        *,
        resolved: bool | None,
        now_ts: float | None = None,
    ) -> None:
        phrase = str(text or "").strip()
        if not phrase:
            return
        intent = str(intent_class or "").strip().lower()
        unresolved = intent in {"action", "hybrid"} and resolved is not True
        if now_ts is None:
            timestamp = time.time()
        else:
            try:
                timestamp = float(now_ts)
            except (TypeError, ValueError):
                timestamp = time.time()
        if not math.isfinite(timestamp) or timestamp < 0.0:
            timestamp = time.time()
        payload = {
            "text": phrase[:280],
            "intent": intent,
            "timestamp": timestamp,
            "unresolved": unresolved,
        }
        self._followup_carryover = payload

    @staticmethod
    def _turn_tool_summaries_since(started_at: float) -> list[dict[str, Any]]:
        with suppress(Exception):
            summaries = list_summaries(limit=200)
            if isinstance(summaries, list):
                matched: list[dict[str, Any]] = []
                for item in summaries:
                    if not isinstance(item, dict):
                        continue
                    timestamp_raw = item.get("timestamp")
                    try:
                        timestamp = float(timestamp_raw)
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(timestamp) or timestamp < started_at:
                        continue
                    name = str(item.get("name", "")).strip().lower()
                    if name in {"system_status", "system_status_contract", "tool_summary", "tool_summary_text"}:
                        continue
                    matched.append(item)
                return matched
        return []

    @staticmethod
    def _completion_success_from_summaries(summaries: list[dict[str, Any]]) -> bool | None:
        if not summaries:
            return None
        success_statuses = {"ok", "dry_run", "noop", "cooldown"}
        failure_statuses = {"error", "denied"}
        has_success = any(str(item.get("status", "")).strip().lower() in success_statuses for item in summaries)
        has_failure = any(str(item.get("status", "")).strip().lower() in failure_statuses for item in summaries)
        if has_success:
            return True
        if has_failure:
            return False
        return None

    @staticmethod
    def _tool_call_trace_items(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for item in summaries:
            if not isinstance(item, dict):
                continue
            try:
                duration = float(item.get("duration_ms", 0.0))
            except (TypeError, ValueError):
                duration = 0.0
            if not math.isfinite(duration) or duration < 0.0:
                duration = 0.0
            calls.append(
                {
                    "name": str(item.get("name", "tool")),
                    "status": str(item.get("status", "unknown")),
                    "duration_ms": duration,
                    "detail": str(item.get("detail", "")),
                    "effect": str(item.get("effect", "")),
                    "risk": str(item.get("risk", "")),
                }
            )
        return calls

    @staticmethod
    def _policy_decisions_from_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        for item in summaries:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).strip().lower()
            detail = str(item.get("detail", "")).strip().lower()
            if not status and not detail:
                continue
            if (
                status in {"denied", "dry_run", "cooldown"}
                or detail in {"policy", "circuit_open"}
                or "policy" in detail
                or "preview" in detail
            ):
                decisions.append(
                    {
                        "tool": str(item.get("name", "tool")),
                        "status": status,
                        "detail": detail,
                    }
                )
        return decisions

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
    ) -> None:
        self._turn_trace_seq += 1
        now = time.time()
        total_ms = max(0.0, (now - turn_started_at) * 1000.0)
        stt_ms = max(0.0, float(stt_latency_ms or 0.0))
        llm_ms = max(0.0, float(llm_first_sentence_ms or 0.0))
        tts_ms = max(0.0, float(tts_first_audio_ms or 0.0))
        tool_calls = self._tool_call_trace_items(tool_summaries)
        completion_success = self._completion_success_from_summaries(tool_summaries)
        policy_decisions = self._policy_decisions_from_summaries(tool_summaries)
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
            "turn_id": int(self._turn_trace_seq),
            "timestamp": now,
            "lifecycle": str(lifecycle),
            "intent": str(intent_class),
            "transcript": str(user_text).strip()[:400],
            "followup_carryover_applied": bool(followup_carryover_applied),
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
            "wake_mode": str(getattr(self._voice_controller(), "mode", "unknown")),
            "requester_user": self._active_voice_user(),
            "attention_source": self.presence.attention_source(),
            "turn_choreography": self._turn_choreography_snapshot(),
        }
        self._conversation_traces.appendleft(trace_item)
        self._record_episodic_snapshot(trace_item)
        observability = getattr(self, "_observability", None)
        if observability is not None:
            with suppress(Exception):
                observability.record_event(
                    "conversation_trace",
                    {
                        "turn_id": int(self._turn_trace_seq),
                        "lifecycle": str(lifecycle),
                        "intent": str(intent_class),
                        "tool_count": len(tool_calls),
                        "policy_decision_count": len(policy_decisions),
                    },
                )

    def _record_episodic_snapshot(self, trace_item: dict[str, Any]) -> None:
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

        self._episode_seq = int(getattr(self, "_episode_seq", 0)) + 1
        snapshot = {
            "episode_id": int(self._episode_seq),
            "timestamp": float(trace_item.get("timestamp", time.time()) or time.time()),
            "turn_id": int(trace_item.get("turn_id", 0) or 0),
            "intent": intent,
            "lifecycle": lifecycle,
            "summary": summary,
            "tool_count": int(tool_count),
            "completion_success": completion_success,
            "response_success": response_success,
        }
        timeline = getattr(self, "_episodic_timeline", None)
        if not isinstance(timeline, deque):
            timeline = deque(maxlen=EPISODIC_TIMELINE_MAXLEN)
            self._episodic_timeline = timeline
        timeline.appendleft(snapshot)

    def _operator_episodic_timeline_provider(self, limit: int = 20) -> list[dict[str, Any]]:
        size = max(1, min(200, int(limit)))
        timeline = getattr(self, "_episodic_timeline", None)
        if not isinstance(timeline, deque):
            return []
        return list(timeline)[:size]

    def _operator_conversation_trace_provider(self, limit: int = 20) -> list[dict[str, Any]]:
        size = max(1, min(200, int(limit)))
        return list(self._conversation_traces)[:size]

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
        voice = self._voice_controller()
        command = str(action or "").strip().lower()
        data = payload if isinstance(payload, dict) else {}
        if not command:
            return {
                "ok": False,
                "error": "invalid_action",
                "message": "action is required",
                "available_actions": self._operator_available_actions(),
            }
        if command == "set_wake_mode":
            mode = self._parse_control_choice(data.get("mode"), VALID_WAKE_MODES)
            if mode is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "mode",
                    "expected": sorted(VALID_WAKE_MODES),
                }
            mode = voice.set_mode(mode)
            self._active_control_preset = "custom"
            self._publish_voice_status()
            self._persist_runtime_state_safe()
            return {"ok": True, "mode": mode}
        if command == "set_sleeping":
            sleeping = self._parse_control_bool(data.get("sleeping"))
            if sleeping is None:
                return {"ok": False, "error": "invalid_payload", "field": "sleeping", "expected": "boolean"}
            voice.sleeping = sleeping
            if not sleeping:
                voice.continue_listening()
            self._active_control_preset = "custom"
            self._publish_voice_status()
            self._persist_runtime_state_safe()
            return {"ok": True, "sleeping": voice.sleeping}
        if command == "set_timeout_profile":
            profile = self._parse_control_choice(data.get("profile"), VALID_TIMEOUT_PROFILES)
            if profile is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "profile",
                    "expected": sorted(VALID_TIMEOUT_PROFILES),
                }
            profile = voice.set_timeout_profile(profile)
            self._active_control_preset = "custom"
            self._publish_voice_status()
            self._persist_runtime_state_safe()
            return {"ok": True, "timeout_profile": profile}
        if command == "set_push_to_talk":
            active = self._parse_control_bool(data.get("active"))
            if active is None:
                return {"ok": False, "error": "invalid_payload", "field": "active", "expected": "boolean"}
            voice.set_push_to_talk_active(active)
            self._active_control_preset = "custom"
            self._publish_voice_status()
            self._persist_runtime_state_safe()
            return {"ok": True, "push_to_talk_active": active}
        if command == "set_motion_enabled":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self.config.motion_enabled = enabled
            if enabled:
                with suppress(Exception):
                    self.presence.start()
            else:
                with suppress(Exception):
                    self.presence.stop()
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {"ok": True, "motion_enabled": enabled}
        if command == "set_home_enabled":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self.config.home_enabled = enabled
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {"ok": True, "home_enabled": enabled}
        if command == "set_safe_mode":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self.config.safe_mode_enabled = enabled
            service_tools.set_safe_mode(enabled)
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {"ok": True, "safe_mode_enabled": enabled}
        if command == "set_tts_enabled":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self._tts_output_enabled = enabled
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {"ok": True, "tts_enabled": enabled}
        if command == "set_persona_style":
            style = self._parse_control_choice(data.get("style"), VALID_PERSONA_STYLES)
            if style is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "style",
                    "expected": sorted(VALID_PERSONA_STYLES),
                }
            self._set_persona_style(style)
            self._personality_preview_snapshot = None
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {"ok": True, "persona_style": style}
        if command == "set_backchannel_style":
            style = self._parse_control_choice(data.get("style"), VALID_BACKCHANNEL_STYLES)
            if style is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "style",
                    "expected": sorted(VALID_BACKCHANNEL_STYLES),
                }
            self.config.backchannel_style = style
            self.presence.set_backchannel_style(style)
            self._personality_preview_snapshot = None
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {"ok": True, "backchannel_style": style}
        if command == "set_voice_profile":
            user = str(data.get("user", "")).strip().lower()
            if not user:
                return {"ok": False, "error": "invalid_payload", "field": "user", "expected": "non-empty string"}
            verbosity = self._parse_control_choice(data.get("verbosity"), VALID_VOICE_PROFILE_VERBOSITY)
            confirmations = self._parse_control_choice(data.get("confirmations"), VALID_VOICE_PROFILE_CONFIRMATIONS)
            pace = self._parse_control_choice(data.get("pace"), VALID_VOICE_PROFILE_PACE)
            profile_patch: dict[str, str] = {}
            if "verbosity" in data:
                if verbosity is None:
                    return {
                        "ok": False,
                        "error": "invalid_payload",
                        "field": "verbosity",
                        "expected": sorted(VALID_VOICE_PROFILE_VERBOSITY),
                    }
                profile_patch["verbosity"] = verbosity
            if "confirmations" in data:
                if confirmations is None:
                    return {
                        "ok": False,
                        "error": "invalid_payload",
                        "field": "confirmations",
                        "expected": sorted(VALID_VOICE_PROFILE_CONFIRMATIONS),
                    }
                profile_patch["confirmations"] = confirmations
            if "pace" in data:
                if pace is None:
                    return {
                        "ok": False,
                        "error": "invalid_payload",
                        "field": "pace",
                        "expected": sorted(VALID_VOICE_PROFILE_PACE),
                    }
                profile_patch["pace"] = pace
            if not profile_patch:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "message": "provide at least one of verbosity, confirmations, or pace",
                }
            profiles = getattr(self, "_voice_user_profiles", {})
            if not isinstance(profiles, dict):
                profiles = {}
            entry = profiles.get(user, {})
            if not isinstance(entry, dict):
                entry = {}
            merged = {**entry, **profile_patch}
            profiles[user] = merged
            self._voice_user_profiles = profiles
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            self._publish_voice_status()
            return {"ok": True, "user": user, "profile": merged}
        if command == "clear_voice_profile":
            user = str(data.get("user", "")).strip().lower()
            if not user:
                return {"ok": False, "error": "invalid_payload", "field": "user", "expected": "non-empty string"}
            profiles = getattr(self, "_voice_user_profiles", {})
            removed = False
            if isinstance(profiles, dict) and user in profiles:
                profiles.pop(user, None)
                removed = True
            self._voice_user_profiles = profiles if isinstance(profiles, dict) else {}
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            self._publish_voice_status()
            return {"ok": True, "user": user, "removed": removed}
        if command == "list_voice_profiles":
            profiles = getattr(self, "_voice_user_profiles", {})
            snapshot = {
                str(name): dict(value)
                for name, value in profiles.items()
                if isinstance(value, dict)
            } if isinstance(profiles, dict) else {}
            active_user = self._active_voice_user()
            return {
                "ok": True,
                "active_user": active_user,
                "active_profile": self._active_voice_profile(user=active_user),
                "profiles": snapshot,
            }
        if command == "apply_control_preset":
            preset = self._parse_control_choice(data.get("preset"), VALID_CONTROL_PRESETS)
            if preset is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "preset",
                    "expected": sorted(VALID_CONTROL_PRESETS),
                }
            applied = self._apply_control_preset(preset)
            if applied is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "preset",
                    "expected": sorted(VALID_CONTROL_PRESETS),
                }
            return {"ok": True, "preset": preset, "runtime_profile": applied}
        if command == "export_runtime_profile":
            return {"ok": True, "runtime_profile": self._runtime_profile_snapshot()}
        if command == "import_runtime_profile":
            profile = data.get("profile")
            if not isinstance(profile, dict):
                return {"ok": False, "error": "invalid_payload", "field": "profile", "expected": "object"}
            applied = self._apply_runtime_profile(profile, mark_custom=True)
            return {"ok": True, "runtime_profile": applied}
        if command == "preview_personality":
            persona_style = self._parse_control_choice(data.get("persona_style"), VALID_PERSONA_STYLES)
            backchannel_style = self._parse_control_choice(data.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
            if persona_style is None and backchannel_style is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "message": "provide persona_style and/or backchannel_style",
                    "expected": {
                        "persona_style": sorted(VALID_PERSONA_STYLES),
                        "backchannel_style": sorted(VALID_BACKCHANNEL_STYLES),
                    },
                }
            if getattr(self, "_personality_preview_snapshot", None) is None:
                self._personality_preview_snapshot = {
                    "persona_style": str(getattr(self.config, "persona_style", "composed")),
                    "backchannel_style": str(getattr(self.config, "backchannel_style", "balanced")),
                }
            if persona_style is not None:
                self._set_persona_style(persona_style)
            if backchannel_style is not None:
                self.config.backchannel_style = backchannel_style
                self.presence.set_backchannel_style(backchannel_style)
            self._active_control_preset = "custom"
            return {
                "ok": True,
                "preview_active": True,
                "persona_style": str(getattr(self.config, "persona_style", "unknown")),
                "backchannel_style": str(getattr(self.config, "backchannel_style", "unknown")),
                "baseline": dict(self._personality_preview_snapshot or {}),
            }
        if command == "commit_personality_preview":
            was_active = isinstance(getattr(self, "_personality_preview_snapshot", None), dict)
            self._personality_preview_snapshot = None
            self._active_control_preset = "custom"
            self._persist_runtime_state_safe()
            return {
                "ok": True,
                "committed": was_active,
                "preview_active": False,
                "persona_style": str(getattr(self.config, "persona_style", "unknown")),
                "backchannel_style": str(getattr(self.config, "backchannel_style", "unknown")),
            }
        if command == "rollback_personality_preview":
            snapshot = getattr(self, "_personality_preview_snapshot", None)
            if not isinstance(snapshot, dict):
                return {
                    "ok": True,
                    "rolled_back": False,
                    "preview_active": False,
                    "persona_style": str(getattr(self.config, "persona_style", "unknown")),
                    "backchannel_style": str(getattr(self.config, "backchannel_style", "unknown")),
                }
            persona_style = self._parse_control_choice(snapshot.get("persona_style"), VALID_PERSONA_STYLES)
            backchannel_style = self._parse_control_choice(snapshot.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
            if persona_style is not None:
                self._set_persona_style(persona_style)
            if backchannel_style is not None:
                self.config.backchannel_style = backchannel_style
                self.presence.set_backchannel_style(backchannel_style)
            self._personality_preview_snapshot = None
            self._active_control_preset = "custom"
            return {
                "ok": True,
                "rolled_back": True,
                "preview_active": False,
                "persona_style": str(getattr(self.config, "persona_style", "unknown")),
                "backchannel_style": str(getattr(self.config, "backchannel_style", "unknown")),
            }
        if command == "clear_inbound_webhooks":
            result = await service_tools.webhook_inbound_clear({})
            text = result.get("content", [{}])[0].get("text", "")
            return {"ok": True, "message": text}
        if command == "skills_reload":
            self._skills.discover()
            self._publish_skills_status()
            return {"ok": True, "skills": self._skills.status_snapshot()}
        if command == "skills_enable":
            name = str(data.get("name", "")).strip().lower()
            if not name:
                return {"ok": False, "error": "invalid_payload", "field": "name", "expected": "non-empty string"}
            ok, detail = self._skills.enable_skill(name)
            self._publish_skills_status()
            return {"ok": ok, "detail": detail, "name": name}
        if command == "skills_disable":
            name = str(data.get("name", "")).strip().lower()
            if not name:
                return {"ok": False, "error": "invalid_payload", "field": "name", "expected": "non-empty string"}
            ok, detail = self._skills.disable_skill(name)
            self._publish_skills_status()
            return {"ok": ok, "detail": detail, "name": name}
        return {
            "ok": False,
            "error": "invalid_action",
            "message": "unknown action",
            "available_actions": self._operator_available_actions(),
        }

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
        """Main conversation loop."""
        try:
            self.start()
            if self.tts is not None:
                self._tts_task = asyncio.create_task(self._tts_loop(), name="tts")
            self._listen_task = asyncio.create_task(self._listen_loop(), name="listen")
            if self.config.watchdog_enabled:
                self._watchdog_task = asyncio.create_task(self._watchdog_loop(), name="watchdog")
            await self._start_operator_server()
            print("\n  JARVIS is online. Speak to begin.\n")
            print("  Press Ctrl+C to exit.\n")
            for line in self._startup_summary_lines():
                print(f"  {line}")
            for warning in getattr(self.config, "startup_warnings", []):
                print(f"  WARNING: {warning}")
            print("")

            while True:
                utterance = await self._utterance_queue.get()

                # Transcribe (run in executor to not block event loop)
                self.presence.signals.state = State.THINKING
                text = await asyncio.get_event_loop().run_in_executor(
                    None, self._transcribe_with_fallback, utterance
                )
                stt_elapsed = time.monotonic() - self._last_doa_update if self._last_doa_update else None
                stt_latency_ms = (stt_elapsed * 1000.0) if stt_elapsed is not None else None
                if stt_elapsed is not None:
                    log.info("STT latency: %.0fms", stt_elapsed * 1000.0)
                    self._telemetry["stt_latency_total_ms"] += stt_elapsed * 1000.0
                    self._telemetry["stt_latency_count"] += 1.0
                self._publish_voice_status()
                if not text.strip():
                    self.presence.signals.state = State.IDLE
                    self._publish_voice_status()
                    continue

                decision = self._voice_controller().process_transcript(text)
                if decision.reply:
                    if self.tts:
                        await self._tts_queue.put((self._active_response_id, decision.reply, True, 0.0))
                    else:
                        print(f"  JARVIS: {decision.reply}")
                if not decision.accepted:
                    self.presence.signals.state = State.IDLE
                    self._publish_voice_status()
                    continue
                text = decision.text
                utterance_duration_sec = float(len(utterance)) / float(self.config.sample_rate)
                turn_count = max(1.0, float(self._telemetry.get("turns", 0.0)))
                interruption_likelihood = float(self._telemetry.get("barge_ins", 0.0)) / turn_count
                self._voice_controller().register_utterance(
                    text,
                    duration_sec=utterance_duration_sec,
                    interruption_likelihood=interruption_likelihood,
                )

                repair_resolved_this_turn = False
                if self._awaiting_confirmation:
                    normalized = text.strip().lower()
                    intent = self._voice_controller().confirmation_intent(normalized)
                    if intent == "confirm" and self._pending_text:
                        self._awaiting_confirmation = False
                        text = self._pending_text
                        self._pending_text = None
                    elif intent == "deny":
                        self._awaiting_confirmation = False
                        self._pending_text = None
                        if self.tts:
                            await self._tts_queue.put((self._active_response_id, "Understood.", True, 0.0))
                        else:
                            print("  JARVIS: Understood.")
                        self.presence.signals.state = State.IDLE
                        self._publish_voice_status()
                        continue
                    elif intent == "repeat":
                        if self.tts:
                            await self._tts_queue.put(
                                (
                                    self._active_response_id,
                                    "Please say confirm to proceed or deny to cancel.",
                                    True,
                                    0.0,
                                )
                            )
                        else:
                            print("  JARVIS: Please say confirm to proceed or deny to cancel.")
                        self.presence.signals.state = State.LISTENING
                        self._awaiting_confirmation = True
                        self._publish_voice_status()
                        continue
                    else:
                        self._awaiting_confirmation = False
                        self._pending_text = None

                if self._awaiting_repair_confirmation:
                    normalized = text.strip().lower()
                    intent = self._voice_controller().confirmation_intent(normalized)
                    words = re.findall(r"[a-z0-9']+", normalized)
                    if intent == "confirm" and self._repair_candidate_text:
                        text = self._repair_candidate_text
                        self._awaiting_repair_confirmation = False
                        self._repair_candidate_text = None
                        repair_resolved_this_turn = True
                    elif intent in {"deny", "repeat"} and len(words) <= 2:
                        if self.tts:
                            await self._tts_queue.put((self._active_response_id, REPAIR_REPEAT_PROMPT, True, 0.0))
                        else:
                            print(f"  JARVIS: {REPAIR_REPEAT_PROMPT}")
                        self.presence.signals.state = State.LISTENING
                        self._awaiting_repair_confirmation = True
                        self._publish_voice_status()
                        continue
                    else:
                        self._awaiting_repair_confirmation = False
                        self._repair_candidate_text = None
                        repair_resolved_this_turn = True

                intent_class = self._classify_user_intent(text)
                self._telemetry["intent_turns_total"] += 1.0
                if intent_class == "action":
                    self._telemetry["intent_action_turns"] += 1.0
                elif intent_class == "hybrid":
                    self._telemetry["intent_hybrid_turns"] += 1.0
                else:
                    self._telemetry["intent_answer_turns"] += 1.0
                looks_like_correction = self._looks_like_user_correction(text)
                if looks_like_correction:
                    self._telemetry["intent_corrections"] += 1.0

                turn_started_at = time.time()
                if not repair_resolved_this_turn and self._requires_stt_repair(text, intent_class):
                    self._awaiting_repair_confirmation = True
                    self._repair_candidate_text = text
                    prompt = self._repair_prompt(text)
                    if self.tts:
                        await self._tts_queue.put((self._active_response_id, prompt, True, 0.0))
                    else:
                        print(f"  JARVIS: {prompt}")
                    self.presence.signals.state = State.LISTENING
                    self._publish_voice_status()
                    self._record_conversation_trace(
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

                memory_correction = self._parse_memory_correction_command(text)
                if memory_correction is not None:
                    tool_name, payload = memory_correction
                    if tool_name == "memory_forget":
                        result = await service_tools.memory_forget(payload)
                    else:
                        result = await service_tools.memory_update(payload)
                    if not looks_like_correction:
                        self._telemetry["intent_corrections"] += 1.0
                    turn_tool_summaries = self._turn_tool_summaries_since(turn_started_at)
                    completion_outcome = self._completion_success_from_summaries(turn_tool_summaries)
                    if completion_outcome is not None:
                        self._telemetry["intent_completion_total"] += 1.0
                        if completion_outcome:
                            self._telemetry["intent_completion_success"] += 1.0
                    correction_succeeded = not bool(result.get("isError", False))
                    self._update_followup_carryover(
                        text,
                        intent_class,
                        resolved=correction_succeeded,
                        now_ts=turn_started_at,
                    )
                    reply = str(result.get("content", [{}])[0].get("text", "")).strip() or "Done."
                    if self.tts:
                        await self._tts_queue.put((self._active_response_id, reply, True, 0.0))
                    else:
                        print(f"  JARVIS: {reply}")
                    self.presence.signals.state = State.IDLE
                    self._publish_voice_status()
                    self._record_conversation_trace(
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

                if self._requires_confirmation(time.monotonic()):
                    self._awaiting_confirmation = True
                    self._pending_text = text
                    self._telemetry["fallback_responses"] += 1.0
                    self._update_followup_carryover(
                        text,
                        intent_class,
                        resolved=False,
                        now_ts=turn_started_at,
                    )
                    if self.tts:
                        await self._tts_queue.put((self._active_response_id, CONFIRMATION_PHRASE, True, 0.0))
                    else:
                        print(f"  JARVIS: {CONFIRMATION_PHRASE}")
                    self.presence.signals.state = State.LISTENING
                    self._publish_voice_status()
                    self._record_conversation_trace(
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

                # Get response from Claude and play it
                self._telemetry["turns"] += 1.0
                response_prompt_text, followup_carryover_applied = self._with_followup_carryover(
                    text,
                    now_ts=turn_started_at,
                )
                response_prompt_text = self._with_voice_profile_guidance(response_prompt_text)
                await self._respond_and_speak(response_prompt_text)
                response_success = bool(self._response_started and not self._barge_in.is_set())
                llm_first_sentence_ms = (
                    (self._first_sentence_at - self._response_start_at) * 1000.0
                    if self._first_sentence_at is not None and self._response_start_at is not None
                    else 0.0
                )
                tts_first_audio_ms = (
                    (self._first_audio_at - self._response_start_at) * 1000.0
                    if self._first_audio_at is not None and self._response_start_at is not None
                    else 0.0
                )
                turn_tool_summaries = self._turn_tool_summaries_since(turn_started_at)
                if intent_class in {"answer", "hybrid"}:
                    self._telemetry["intent_answer_total"] += 1.0
                    if response_success:
                        self._telemetry["intent_answer_success"] += 1.0
                completion_outcome: bool | None = None
                if intent_class in {"action", "hybrid"}:
                    completion_outcome = self._completion_success_from_summaries(turn_tool_summaries)
                    if completion_outcome is not None:
                        self._telemetry["intent_completion_total"] += 1.0
                        if completion_outcome:
                            self._telemetry["intent_completion_success"] += 1.0
                if intent_class in {"action", "hybrid"}:
                    resolved: bool | None = completion_outcome is True
                else:
                    resolved = True
                self._update_followup_carryover(
                    text,
                    intent_class,
                    resolved=resolved,
                    now_ts=turn_started_at,
                )
                self._record_conversation_trace(
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
                )
                if int(self._telemetry["turns"]) % TELEMETRY_LOG_EVERY_TURNS == 0:
                    self._refresh_tool_error_counters()
                    snapshot = self._telemetry_snapshot()
                    attention_source = self.presence.attention_source()
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
                self._publish_observability_snapshot()

        except asyncio.CancelledError:
            pass
        finally:
            await self._stop_operator_server()
            if self._listen_task is not None:
                self._listen_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._listen_task
                self._listen_task = None
            if getattr(self, "_watchdog_task", None) is not None:
                self._watchdog_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._watchdog_task
                self._watchdog_task = None
            if self._tts_task is not None:
                self._tts_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._tts_task
                self._tts_task = None
            if self._filler_task is not None:
                self._filler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._filler_task
                self._filler_task = None
            with suppress(Exception):
                await self.brain.close()
            self.stop()

    async def _enqueue_utterance(self, audio: np.ndarray) -> None:
        try:
            self._utterance_queue.put_nowait(audio)
        except asyncio.QueueFull:
            with suppress(asyncio.QueueEmpty):
                self._utterance_queue.get_nowait()
            await self._utterance_queue.put(audio)

    async def _listen_loop(self) -> None:
        """Continuously segment microphone audio into utterances.

        Runs during the entire app lifetime so barge-in works while Jarvis is speaking.
        """

        chunks: list[np.ndarray] = []
        silence_start: float | None = None
        recording = False

        async def process_chunk(chunk_16k: np.ndarray) -> None:
            nonlocal chunks, silence_start, recording

            # Presence signals
            conf = self.vad.confidence(chunk_16k)
            self.presence.signals.vad_energy = max(0.0, min(1.0, conf))
            doa_angle, doa_speech = self.robot.get_doa()
            now = time.monotonic()
            self._last_doa_speech = doa_speech
            self._voice_controller().update_room_from_doa(doa_angle)
            if doa_angle is not None:
                if doa_speech is None or doa_speech:
                    if self._last_doa_angle is None or abs(doa_angle - self._last_doa_angle) >= self.config.doa_change_threshold:
                        self._last_doa_angle = doa_angle
                        self._last_doa_update = now
                        self.presence.signals.doa_angle = doa_angle
                        self.presence.signals.doa_last_seen = now
                else:
                    if self._last_doa_update and (now - self._last_doa_update) > self.config.doa_timeout:
                        self.presence.signals.doa_angle = None
                        self._last_doa_angle = None
            else:
                if self._last_doa_update and (now - self._last_doa_update) > self.config.doa_timeout:
                    self.presence.signals.doa_angle = None
                    self._last_doa_angle = None

            with self._lock:
                assistant_busy = self._speaking

            is_speech = self._compute_turn_taking(
                conf=conf,
                doa_speech=doa_speech,
                assistant_busy=assistant_busy,
                now=now,
            )

            if is_speech:
                if not recording:
                    recording = True
                    self.presence.signals.state = State.LISTENING
                    log.debug("Speech detected")
                silence_start = None
                chunks.append(chunk_16k)

                if assistant_busy and not self._barge_in.is_set():
                    self._barge_in.set()
                    self._flush_output()
                    self._clear_tts_queue()
                    self.presence.signals.state = State.LISTENING
                    self._telemetry["barge_ins"] += 1.0
                    log.info("Barge-in detected")

            elif recording:
                chunks.append(chunk_16k)
                if silence_start is None:
                    silence_start = time.monotonic()
                elif time.monotonic() - silence_start > self._voice_controller().silence_timeout():
                    audio = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)

                    # Reset for the next utterance.
                    self.vad.reset()
                    self.presence.signals.vad_energy = 0.0
                    chunks = []
                    silence_start = None
                    recording = False

                    if audio.size == 0:
                        return

                    duration = len(audio) / self.config.sample_rate
                    if duration >= MIN_UTTERANCE:
                        await self._enqueue_utterance(audio)

            self._publish_voice_status()

        if not self._use_robot_audio:
            _require_sounddevice("local microphone capture")
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=CHUNK_SAMPLES,
            ) as stream:
                while True:
                    data, overflowed = await asyncio.to_thread(stream.read, CHUNK_SAMPLES)
                    if overflowed:
                        log.warning("Audio input buffer overflowed")
                    await process_chunk(data[:, 0])
                    await asyncio.sleep(0)

        else:
            pending_chunks: deque[np.ndarray] = deque()
            pending_len = 0
            while True:
                raw = self.robot.get_audio_sample()
                if raw is None:
                    await asyncio.sleep(0.005)
                    continue

                mono = _to_mono(raw)
                mono_16k = _resample_audio(mono, self._robot_input_sr, self.config.sample_rate)
                if mono_16k.size == 0:
                    await asyncio.sleep(0)
                    continue

                pending_chunks.append(mono_16k)
                pending_len += int(mono_16k.size)

                while pending_len >= CHUNK_SAMPLES:
                    needed = CHUNK_SAMPLES
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
                    pending_len -= CHUNK_SAMPLES
                    await process_chunk(chunk)

                await asyncio.sleep(0)

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
        """Get Claude's response and stream TTS with barge-in support."""
        self._barge_in.clear()
        self._clear_tts_queue()
        self._response_id += 1
        self._active_response_id = self._response_id
        self._response_started = False
        self._first_sentence_at = None
        self._first_audio_at = None
        self._response_start_at = time.monotonic()
        self._tts_gain = 1.0

        if self._filler_task is not None:
            self._filler_task.cancel()
        if self.tts is not None:
            self._filler_task = asyncio.create_task(self._thinking_filler(), name="thinking-filler")

        with self._lock:
            self._speaking = True

        response_iter = self.brain.respond(text)

        try:
            async for sentence in response_iter:
                if self._barge_in.is_set():
                    log.info("Barge-in — stopping response")
                    self._flush_output()
                    self._clear_tts_queue()
                    self.robot.stop_sequence()
                    break

                if not self._response_started:
                    self._response_started = True
                    self._first_sentence_at = time.monotonic()
                    if self._response_start_at is not None:
                        latency_ms = (self._first_sentence_at - self._response_start_at) * 1000.0
                        self._telemetry["llm_first_sentence_total_ms"] += latency_ms
                        self._telemetry["llm_first_sentence_count"] += 1.0
                        log.info(
                            "LLM first sentence latency: %.0fms",
                            latency_ms,
                        )
                    if self._filler_task is not None:
                        self._filler_task.cancel()

                if self.tts:
                    pause = self._confidence_pause(sentence)
                    await self._tts_queue.put((self._active_response_id, sentence, False, pause))
                else:
                    print(f"  JARVIS: {sentence}")

        finally:
            with suppress(Exception):
                await response_iter.aclose()
            with self._lock:
                self._speaking = False
            if not self._barge_in.is_set():
                self.presence.signals.state = State.IDLE
                self._voice_controller().continue_listening()
            if self._filler_task is not None:
                self._filler_task.cancel()
            self._publish_voice_status()

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
        if self.presence.signals.face_last_seen and (now - self.presence.signals.face_last_seen) <= ATTENTION_RECENCY_SEC:
            return 1.0
        if self.presence.signals.hand_last_seen and (now - self.presence.signals.hand_last_seen) <= ATTENTION_RECENCY_SEC:
            return 0.8
        if self.presence.signals.doa_last_seen and (now - self.presence.signals.doa_last_seen) <= ATTENTION_RECENCY_SEC:
            return 0.5
        return 0.0

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
        if chunk.size == 0:
            return chunk
        if not np.isfinite(chunk).all():
            chunk = np.nan_to_num(chunk, nan=0.0, posinf=1.0, neginf=-1.0)
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        if not np.isfinite(rms) or rms <= 1e-6:
            return chunk
        desired_gain = max(0.5, min(2.0, TTS_TARGET_RMS / rms))
        if not np.isfinite(desired_gain):
            desired_gain = 1.0
        self._tts_gain += (desired_gain - self._tts_gain) * TTS_GAIN_SMOOTH
        normalized = chunk * self._tts_gain
        return np.clip(normalized, -1.0, 1.0)

    def _confidence_pause(self, sentence: str) -> float:
        lowered = sentence.lower()
        if any(token in lowered for token in TTS_LOW_CONFIDENCE_WORDS):
            pause = TTS_CONFIDENCE_PAUSE_SEC
        else:
            pause = TTS_SENTENCE_PAUSE_SEC
        pace = self._active_voice_profile().get("pace", "normal")
        if pace == "slow":
            return pause * 1.25
        if pace == "fast":
            return pause * 0.8
        return pause


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
