"""Lifecycle runtime helpers for Jarvis startup and shutdown."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Callable

from jarvis.tools.services import set_runtime_voice_state


def start(
    runtime: Any,
    *,
    require_sounddevice_fn: Callable[[str], None],
    sd_module: Any,
    build_face_tracker_fn: Callable[[], Any],
    build_hand_tracker_fn: Callable[[], Any],
    sleep_fn: Callable[[float], None],
    logger: Any,
) -> None:
    """Initialize runtime subsystems and media pipelines."""
    if runtime._started:
        return
    runtime._started = True
    try:
        blockers = runtime._startup_blockers()
        if blockers:
            raise RuntimeError("; ".join(blockers))

        with suppress(Exception):
            runtime._skills.discover()
        runtime._publish_skills_status()

        observability = getattr(runtime, "_observability", None)
        if observability is not None:
            observability.start()
            observability.record_event("startup", {"mode": "simulation" if runtime.robot.sim else "hardware"})
            runtime._publish_observability_status()

        runtime.robot.connect()
        if runtime.config.motion_enabled:
            runtime.presence.start()

        runtime._use_robot_audio = not runtime.robot.sim

        if not runtime.args.no_vision and not runtime.robot.sim:
            runtime.face_tracker = build_face_tracker_fn()
            runtime.face_tracker.start()

            if runtime.config.hand_track_enabled:
                runtime.hand_tracker = build_hand_tracker_fn()
                runtime.hand_tracker.start()

        if runtime._use_robot_audio:
            runtime.robot.start_audio(recording=True, playing=runtime.tts is not None)
            sleep_fn(0.2)  # give media pipelines a moment to warm up
            runtime._robot_input_sr = runtime.robot.get_input_audio_samplerate() or runtime.config.sample_rate
            runtime._robot_output_sr = runtime.robot.get_output_audio_samplerate() or runtime.config.sample_rate
            logger.info(
                "Using Reachy Mini media audio (in=%dHz out=%dHz)",
                runtime._robot_input_sr,
                runtime._robot_output_sr,
            )
        else:
            if runtime.tts is not None:
                require_sounddevice_fn("local audio playback")
                runtime._output_stream = sd_module.OutputStream(
                    samplerate=runtime.config.sample_rate,
                    channels=1,
                    dtype="float32",
                )
                runtime._output_stream.start()

        logger.info("Jarvis is online.")
        runtime._publish_voice_status()
        runtime._publish_observability_status()
    except Exception:
        runtime.stop()
        raise


def stop(runtime: Any, *, logger: Any) -> None:
    """Shut down all runtime subsystems."""
    if not runtime._started:
        return
    runtime._save_runtime_state()
    observability = getattr(runtime, "_observability", None)
    if observability is not None:
        runtime._publish_observability_snapshot(force=True)
        with suppress(Exception):
            observability.record_event("shutdown", {"reason": "stop_called"})
        with suppress(Exception):
            observability.stop()
        with suppress(Exception):
            observability.close()
    if runtime._output_stream:
        with suppress(Exception):
            runtime._output_stream.stop()
        with suppress(Exception):
            runtime._output_stream.close()
        runtime._output_stream = None
    if runtime.face_tracker:
        with suppress(Exception):
            runtime.face_tracker.stop()
        runtime.face_tracker = None
    if runtime._use_robot_audio:
        with suppress(Exception):
            runtime.robot.stop_audio(recording=True, playing=True)
    if runtime.hand_tracker:
        with suppress(Exception):
            runtime.hand_tracker.stop()
        runtime.hand_tracker = None
    if runtime.config.motion_enabled:
        with suppress(Exception):
            runtime.presence.stop()
    with suppress(Exception):
        runtime.robot.disconnect()
    runtime._started = False
    set_runtime_voice_state(
        {
            "mode": "offline",
            "followup_active": False,
            "sleeping": False,
            "active_room": "unknown",
            "stt_diagnostics": runtime._default_stt_diagnostics(),
        }
    )
    runtime._publish_observability_status()
    runtime._publish_skills_status()
    logger.info("Jarvis offline.")
