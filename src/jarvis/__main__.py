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
import logging
import time
import threading
from pathlib import Path
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
from jarvis.operator_server import OperatorServer
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
from jarvis.runtime_operator_server import (
    operator_events_provider as _runtime_operator_events_provider,
    operator_metrics_provider as _runtime_operator_metrics_provider,
    start_operator_server as _runtime_start_operator_server,
    startup_diagnostics_provider as _runtime_startup_diagnostics_provider,
    stop_operator_server as _runtime_stop_operator_server,
)
from jarvis.runtime_observability_status import (
    default_observability_status_snapshot as _runtime_default_observability_status_snapshot,
    publish_observability_status as _runtime_publish_observability_status,
)
from jarvis.runtime_observability_snapshot import (
    publish_observability_snapshot as _runtime_publish_observability_snapshot,
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
    attention_confidence as _turn_attention_confidence,
    classify_user_intent as _turn_classify_user_intent,
    compute_turn_taking as _turn_compute_turn_taking,
    completion_success_from_summaries as _turn_completion_success_from_summaries,
    is_followup_carryover_candidate as _turn_is_followup_carryover_candidate,
    looks_like_user_correction as _turn_looks_like_user_correction,
    policy_decisions_from_summaries as _turn_policy_decisions_from_summaries,
    requires_confirmation as _turn_requires_confirmation,
    requires_stt_repair as _turn_requires_stt_repair,
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
    refresh_tool_error_counters as _runtime_refresh_tool_error_counters,
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
    startup_summary_lines as _runtime_startup_summary_lines,
)
from jarvis.runtime_conversation import (
    listen_loop as _runtime_listen_loop,
    respond_and_speak as _runtime_respond_and_speak,
    run as _runtime_run,
)
from jarvis.runtime_lifecycle import (
    start as _runtime_start,
    stop as _runtime_stop,
)
from jarvis.runtime_voice_status import (
    apply_turn_choreography as _runtime_apply_turn_choreography,
    publish_voice_status as _runtime_publish_voice_status,
    turn_choreography_snapshot as _runtime_turn_choreography_snapshot,
)
from jarvis.runtime_audio_output import (
    clear_tts_queue as _runtime_clear_tts_queue,
    flush_output as _runtime_flush_output,
    play_audio_chunk as _runtime_play_audio_chunk,
    tts_loop as _runtime_tts_loop,
)
from jarvis.runtime_voice_profile import (
    active_voice_profile as _runtime_active_voice_profile,
    active_voice_user as _runtime_active_voice_user,
    parse_control_bool as _runtime_parse_control_bool,
    parse_control_choice as _runtime_parse_control_choice,
    with_voice_profile_guidance as _runtime_with_voice_profile_guidance,
)
from jarvis.runtime_preferences import (
    learn_voice_preferences as _runtime_learn_voice_preferences,
    set_persona_style as _runtime_set_persona_style,
)
from jarvis.runtime_multimodal import (
    multimodal_grounding_snapshot_for_runtime as _runtime_multimodal_grounding_snapshot_for_runtime,
)
from jarvis.runtime_watchdog import watchdog_loop as _runtime_watchdog_loop
from jarvis.runtime_bootstrap import (
    apply_cli_overrides as _runtime_apply_cli_overrides,
    build_observability_store as _runtime_build_observability_store,
    build_skill_registry as _runtime_build_skill_registry,
    build_voice_attention_controller as _runtime_build_voice_attention_controller,
    initialize_runtime_fields as _runtime_initialize_runtime_fields,
)
from jarvis.runtime_entrypoint import (
    maybe_run_backup_or_restore as _runtime_maybe_run_backup_or_restore,
    run_jarvis_event_loop as _runtime_run_jarvis_event_loop,
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
        _runtime_apply_cli_overrides(self.config, args)

        self._voice_attention = _runtime_build_voice_attention_controller(self.config)
        self._runtime_state_path = Path(self.config.runtime_state_path).expanduser()

        self._skills = _runtime_build_skill_registry(self.config)
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

        self._observability = _runtime_build_observability_store(self.config)
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

        _runtime_initialize_runtime_fields(
            self,
            state_idle_value=str(State.IDLE.value),
            conversation_trace_maxlen=CONVERSATION_TRACE_MAXLEN,
            episodic_timeline_maxlen=EPISODIC_TIMELINE_MAXLEN,
            runtime_invariant_history_maxlen=RUNTIME_INVARIANT_HISTORY_MAXLEN,
        )
        self._load_runtime_state()
        self._publish_voice_status()
        self._publish_skills_status()
        self._publish_observability_status()

    def _build_face_tracker(self) -> Any:
        from jarvis.vision.face_tracker import FaceTracker

        return FaceTracker(
            presence=self.presence,
            get_frame=self.robot.get_frame,
            model_path=self.config.yolo_model,
            fps=self.config.face_track_fps,
        )

    def _build_hand_tracker(self) -> Any:
        from jarvis.vision.hand_tracker import HandTracker

        return HandTracker(
            presence=self.presence,
            get_frame=self.robot.get_frame,
            fps=self.config.face_track_fps,
        )

    def start(self) -> None:
        """Initialize all subsystems."""
        _runtime_start(
            self,
            require_sounddevice_fn=_require_sounddevice,
            sd_module=sd,
            build_face_tracker_fn=self._build_face_tracker,
            build_hand_tracker_fn=self._build_hand_tracker,
            sleep_fn=time.sleep,
            logger=log,
        )

    def _startup_summary_lines(self) -> list[str]:
        return _runtime_startup_summary_lines(
            self,
            normalize_operator_auth_mode_fn=_runtime_normalize_operator_auth_mode,
            operator_auth_risk_fn=_runtime_operator_auth_risk,
            valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
            tool_service_error_codes=TOOL_SERVICE_ERROR_CODES,
            telemetry_service_error_details=TELEMETRY_SERVICE_ERROR_DETAILS,
            telemetry_storage_error_details=TELEMETRY_STORAGE_ERROR_DETAILS,
        )

    def _publish_voice_status(self) -> None:
        _runtime_publish_voice_status(
            self,
            set_runtime_voice_state_fn=set_runtime_voice_state,
            cues_by_state=TURN_CHOREOGRAPHY_CUES,
            idle_state_value=str(State.IDLE.value),
        )

    def _apply_turn_choreography(self, state: State) -> None:
        _runtime_apply_turn_choreography(
            self,
            state,
            cues_by_state=TURN_CHOREOGRAPHY_CUES,
        )

    def _turn_choreography_snapshot(self) -> dict[str, Any]:
        return _runtime_turn_choreography_snapshot(
            self,
            idle_state_value=str(State.IDLE.value),
        )

    def _publish_skills_status(self) -> None:
        skills = getattr(self, "_skills", None)
        if skills is None:
            set_runtime_skills_state({"enabled": False, "loaded_count": 0, "enabled_count": 0, "skills": []})
            return
        set_runtime_skills_state(skills.status_snapshot())

    def _publish_observability_status(self) -> None:
        _runtime_publish_observability_status(
            self,
            set_runtime_observability_state_fn=set_runtime_observability_state,
            default_snapshot_fn=_runtime_default_observability_status_snapshot,
        )

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
        return _runtime_learn_voice_preferences(
            self,
            text,
            now_ts=now_ts,
            valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
            valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
            valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
            valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
        )

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
        _runtime_refresh_tool_error_counters(
            self,
            list_summaries_fn=list_summaries,
            tool_service_error_codes=TOOL_SERVICE_ERROR_CODES,
            storage_error_details=TELEMETRY_STORAGE_ERROR_DETAILS,
            service_error_details=TELEMETRY_SERVICE_ERROR_DETAILS,
        )

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
        _runtime_publish_observability_snapshot(
            self,
            force=force,
            list_summaries_fn=list_summaries,
            logger=log,
        )

    async def _watchdog_loop(self) -> None:
        await _runtime_watchdog_loop(
            self,
            state_idle=State.IDLE,
            state_listening=State.LISTENING,
            state_thinking=State.THINKING,
            state_speaking=State.SPEAKING,
            poll_sec=WATCHDOG_POLL_SEC,
            logger=log,
        )

    async def _operator_status_provider(self) -> dict[str, Any]:
        return await _runtime_operator_status_provider(
            self,
            valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
            valid_control_presets=VALID_CONTROL_PRESETS,
            system_status_fn=service_tools.system_status,
        )

    def _startup_diagnostics_provider(self) -> list[str]:
        return _runtime_startup_diagnostics_provider(self)

    def _operator_metrics_provider(self) -> str:
        return _runtime_operator_metrics_provider(self)

    def _operator_events_provider(self) -> list[dict[str, Any]]:
        return _runtime_operator_events_provider(self)

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
        _runtime_set_persona_style(self, style)

    async def _operator_control_handler(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await _runtime_handle_operator_control(self, action, payload)

    async def _start_operator_server(self) -> None:
        await _runtime_start_operator_server(
            self,
            operator_server_class=OperatorServer,
            record_inbound_webhook_event_fn=service_tools.record_inbound_webhook_event,
            logger=log,
        )

    async def _stop_operator_server(self) -> None:
        await _runtime_stop_operator_server(self)

    def stop(self) -> None:
        """Shut down all subsystems."""
        _runtime_stop(self, logger=log)

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
        _runtime_flush_output(self)

    def _play_audio_chunk(self, audio_16k: np.ndarray) -> None:
        _runtime_play_audio_chunk(
            self,
            audio_16k,
            resample_audio_fn=_resample_audio,
            logger=log,
        )

    async def _respond_and_speak(self, text: str) -> None:
        await _runtime_respond_and_speak(self, text)

    async def _tts_loop(self) -> None:
        """Consume sentences and play TTS in order, with barge-in support."""
        await _runtime_tts_loop(self, logger=log)

    def _clear_tts_queue(self) -> None:
        _runtime_clear_tts_queue(self)

    def _compute_turn_taking(
        self,
        conf: float,
        doa_speech: bool | None,
        assistant_busy: bool,
        now: float,
    ) -> bool:
        attention = self._attention_confidence(now)
        return _turn_compute_turn_taking(
            conf,
            doa_speech,
            assistant_busy,
            attention=attention,
            turn_taking_threshold=TURN_TAKING_THRESHOLD,
            barge_in_threshold=self._voice_controller().barge_in_threshold(),
        )

    def _attention_confidence(self, now: float) -> float:
        return _turn_attention_confidence(
            signals=getattr(self.presence, "signals", None),
            now=now,
            recency_sec=ATTENTION_RECENCY_SEC,
        )

    def _multimodal_grounding_snapshot(self) -> dict[str, Any]:
        return _runtime_multimodal_grounding_snapshot_for_runtime(
            self,
            recency_threshold_sec=ATTENTION_RECENCY_SEC,
        )

    @staticmethod
    def _repair_prompt(text: str) -> str:
        excerpt = " ".join(str(text or "").split())
        if len(excerpt) > 140:
            excerpt = excerpt[:137].rstrip() + "..."
        return REPAIR_CONFIRMATION_TEMPLATE.format(text=excerpt)

    def _requires_stt_repair(self, text: str, intent_class: str) -> bool:
        return _turn_requires_stt_repair(
            text,
            intent_class,
            looks_like_user_correction_fn=self._looks_like_user_correction,
            diagnostics=self._stt_diagnostics_snapshot(),
            repair_min_words=REPAIR_MIN_WORDS,
            repair_confidence_threshold=REPAIR_CONFIDENCE_THRESHOLD,
        )

    def _requires_confirmation(self, now: float) -> bool:
        profile = self._active_voice_profile()
        return _turn_requires_confirmation(
            attention=self._attention_confidence(now),
            confirmations=str(profile.get("confirmations", "standard")),
            last_doa_speech=self._last_doa_speech,
            intended_query_min_attention=INTENDED_QUERY_MIN_ATTENTION,
        )

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

    if _runtime_maybe_run_backup_or_restore(
        args,
        config_class=Config,
        create_backup_bundle_fn=create_backup_bundle,
        restore_backup_bundle_fn=restore_backup_bundle,
    ):
        return

    jarvis = Jarvis(args)
    _runtime_run_jarvis_event_loop(jarvis)


if __name__ == "__main__":
    main()
