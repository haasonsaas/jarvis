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
AFFIRMATIONS = {"yes", "yeah", "yep", "yup", "correct", "affirmative", "sure", "please"}
NEGATIONS = {"no", "nope", "nah", "negative"}
TELEMETRY_LOG_EVERY_TURNS = 5
TELEMETRY_STORAGE_ERROR_DETAILS = TOOL_STORAGE_ERROR_DETAILS
TELEMETRY_SERVICE_ERROR_DETAILS = TOOL_SERVICE_ERROR_CODES - TELEMETRY_STORAGE_ERROR_DETAILS
WATCHDOG_POLL_SEC = 0.05
CONVERSATION_TRACE_MAXLEN = 200
VALID_PERSONA_STYLES = {"terse", "composed", "friendly"}
VALID_BACKCHANNEL_STYLES = {"quiet", "balanced", "expressive"}
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
        operator_auth_enabled = bool(str(getattr(self.config, "operator_auth_token", "")).strip())
        operator_auth = "auth-required" if operator_auth_enabled else "no-auth"
        return [
            f"Mode: {'simulation' if self.robot.sim else 'hardware'}",
            f"Motion: {'on' if self.config.motion_enabled else 'off'} | Vision: {'on' if not self.args.no_vision and not self.robot.sim else 'off'} | Hands: {'on' if self.config.hand_track_enabled else 'off'}",
            f"Home tools: {'on' if self.config.home_enabled else 'off'}",
            f"Safe mode: {'on' if bool(getattr(self.config, 'safe_mode_enabled', False)) else 'off'}",
            f"Home conversation: {'on' if self.config.home_conversation_enabled else 'off'}",
            f"Wake mode: {wake_mode} | timeout profile: {timeout_profile}",
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
        voice = self._voice_controller()
        status = voice.status()
        try:
            state = self.presence.signals.state
            status["presence_state"] = str(state.value)
            self._apply_turn_choreography(state)
        except Exception:
            status["presence_state"] = "unknown"
        status["turn_choreography"] = self._turn_choreography_snapshot()
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
            }
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
        if (
            bool(getattr(self.config, "operator_server_enabled", False))
            and operator_host not in {"127.0.0.1", "localhost", "::1"}
            and not str(getattr(self.config, "operator_auth_token", "")).strip()
        ):
            blockers.append("STARTUP_STRICT: non-loopback OPERATOR_SERVER_HOST requires OPERATOR_AUTH_TOKEN.")
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
        service_tools.set_safe_mode(bool(getattr(self.config, "safe_mode_enabled", False)))
        self._awaiting_confirmation = bool(payload.get("awaiting_confirmation", False))
        pending = payload.get("pending_text")
        self._pending_text = str(pending) if isinstance(pending, str) else None

    def _save_runtime_state(self) -> None:
        path = getattr(self, "_runtime_state_path", None)
        if path is None or not isinstance(path, Path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        voice = self._voice_controller()
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
                "persona_style": str(self.config.persona_style),
                "backchannel_style": str(self.config.backchannel_style),
            },
            "awaiting_confirmation": bool(getattr(self, "_awaiting_confirmation", False)),
            "pending_text": getattr(self, "_pending_text", None),
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

    def _transcribe_with_fallback(self, audio: np.ndarray) -> str:
        text = self.stt.transcribe(audio)
        if text.strip():
            return text
        fallback = getattr(self, "_stt_secondary", None)
        if fallback is None:
            return text
        recovered = fallback.transcribe(audio)
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
            "auth_required": bool(str(getattr(self.config, "operator_auth_token", "")).strip()),
        }
        status["conversation_trace"] = {
            "recent_count": len(self._conversation_traces),
            "latest_turn_id": latest_turn_id,
        }
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
            "attention_source": self.presence.attention_source(),
            "turn_choreography": self._turn_choreography_snapshot(),
        }
        self._conversation_traces.appendleft(trace_item)
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
            self._publish_voice_status()
            self._persist_runtime_state_safe()
            return {"ok": True, "timeout_profile": profile}
        if command == "set_push_to_talk":
            active = self._parse_control_bool(data.get("active"))
            if active is None:
                return {"ok": False, "error": "invalid_payload", "field": "active", "expected": "boolean"}
            voice.set_push_to_talk_active(active)
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
            self._persist_runtime_state_safe()
            return {"ok": True, "motion_enabled": enabled}
        if command == "set_home_enabled":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self.config.home_enabled = enabled
            self._persist_runtime_state_safe()
            return {"ok": True, "home_enabled": enabled}
        if command == "set_safe_mode":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self.config.safe_mode_enabled = enabled
            service_tools.set_safe_mode(enabled)
            self._persist_runtime_state_safe()
            return {"ok": True, "safe_mode_enabled": enabled}
        if command == "set_tts_enabled":
            enabled = self._parse_control_bool(data.get("enabled"))
            if enabled is None:
                return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
            self._tts_output_enabled = enabled
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
            self._persist_runtime_state_safe()
            return {"ok": True, "backchannel_style": style}
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
        set_runtime_voice_state({"mode": "offline", "followup_active": False, "sleeping": False, "active_room": "unknown"})
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
                    )
                    continue

                if self._requires_confirmation(time.monotonic()):
                    self._awaiting_confirmation = True
                    self._pending_text = text
                    self._telemetry["fallback_responses"] += 1.0
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
                    )
                    continue

                # Get response from Claude and play it
                self._telemetry["turns"] += 1.0
                await self._respond_and_speak(text)
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
                if intent_class in {"action", "hybrid"}:
                    completion_outcome = self._completion_success_from_summaries(turn_tool_summaries)
                    if completion_outcome is not None:
                        self._telemetry["intent_completion_total"] += 1.0
                        if completion_outcome:
                            self._telemetry["intent_completion_success"] += 1.0
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

    def _requires_confirmation(self, now: float) -> bool:
        attention = self._attention_confidence(now)
        if attention >= INTENDED_QUERY_MIN_ATTENTION:
            return False
        if self._last_doa_speech is True:
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
            return TTS_CONFIDENCE_PAUSE_SEC
        return TTS_SENTENCE_PAUSE_SEC


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
