from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jarvis.runtime_lifecycle import start, stop


def _runtime_stub() -> SimpleNamespace:
    return SimpleNamespace(
        _started=False,
        _startup_blockers=lambda: [],
        _skills=SimpleNamespace(discover=MagicMock()),
        _publish_skills_status=MagicMock(),
        _publish_observability_status=MagicMock(),
        _publish_observability_snapshot=MagicMock(),
        _publish_voice_status=MagicMock(),
        _save_runtime_state=MagicMock(),
        _default_stt_diagnostics=lambda: {"confidence_band": "unknown"},
        _output_stream=None,
        face_tracker=None,
        hand_tracker=None,
        _use_robot_audio=False,
        _observability=None,
        args=SimpleNamespace(no_vision=True),
        tts=None,
        robot=SimpleNamespace(
            sim=True,
            connect=MagicMock(),
            start_audio=MagicMock(),
            stop_audio=MagicMock(),
            disconnect=MagicMock(),
            get_input_audio_samplerate=MagicMock(return_value=None),
            get_output_audio_samplerate=MagicMock(return_value=None),
            get_frame=MagicMock(),
        ),
        presence=SimpleNamespace(start=MagicMock(), stop=MagicMock()),
        config=SimpleNamespace(
            motion_enabled=False,
            hand_track_enabled=False,
            sample_rate=16000,
            yolo_model="model",
            face_track_fps=15,
        ),
        stop=MagicMock(),
    )


def test_start_configures_local_output_stream_when_tts_enabled() -> None:
    runtime = _runtime_stub()
    runtime.tts = object()

    class _FakeStream:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.started = False

        def start(self) -> None:
            self.started = True

    require_sounddevice = MagicMock()
    logger = SimpleNamespace(info=MagicMock())
    sd_module = SimpleNamespace(OutputStream=_FakeStream)

    start(
        runtime,
        require_sounddevice_fn=require_sounddevice,
        sd_module=sd_module,
        build_face_tracker_fn=lambda: None,
        build_hand_tracker_fn=lambda: None,
        sleep_fn=lambda _delay: None,
        logger=logger,
    )

    assert runtime._started is True
    runtime.robot.connect.assert_called_once()
    require_sounddevice.assert_called_once_with("local audio playback")
    assert runtime._output_stream is not None
    assert runtime._output_stream.started is True
    runtime._publish_voice_status.assert_called_once()


def test_start_reraises_and_calls_runtime_stop_on_failure() -> None:
    runtime = _runtime_stub()
    runtime.tts = object()
    require_sounddevice = MagicMock(side_effect=RuntimeError("sounddevice unavailable"))

    with pytest.raises(RuntimeError, match="sounddevice unavailable"):
        start(
            runtime,
            require_sounddevice_fn=require_sounddevice,
            sd_module=SimpleNamespace(OutputStream=MagicMock()),
            build_face_tracker_fn=lambda: None,
            build_hand_tracker_fn=lambda: None,
            sleep_fn=lambda _delay: None,
            logger=SimpleNamespace(info=MagicMock()),
        )

    runtime.stop.assert_called_once()


def test_start_builds_trackers_and_configures_robot_audio_on_hardware() -> None:
    runtime = _runtime_stub()
    runtime.robot.sim = False
    runtime.args.no_vision = False
    runtime.config.motion_enabled = True
    runtime.config.hand_track_enabled = True
    face_tracker = SimpleNamespace(start=MagicMock())
    hand_tracker = SimpleNamespace(start=MagicMock())
    logger = SimpleNamespace(info=MagicMock())
    sleep_fn = MagicMock()

    start(
        runtime,
        require_sounddevice_fn=MagicMock(),
        sd_module=SimpleNamespace(OutputStream=MagicMock()),
        build_face_tracker_fn=lambda: face_tracker,
        build_hand_tracker_fn=lambda: hand_tracker,
        sleep_fn=sleep_fn,
        logger=logger,
    )

    runtime.presence.start.assert_called_once()
    face_tracker.start.assert_called_once()
    hand_tracker.start.assert_called_once()
    runtime.robot.start_audio.assert_called_once_with(recording=True, playing=False)
    sleep_fn.assert_called_once_with(0.2)
    assert runtime._use_robot_audio is True
    assert runtime._robot_input_sr == 16000
    assert runtime._robot_output_sr == 16000


def test_stop_suppresses_component_errors_and_resets_state() -> None:
    runtime = _runtime_stub()
    runtime._started = True
    runtime._use_robot_audio = True
    runtime._output_stream = MagicMock()
    runtime._output_stream.stop.side_effect = RuntimeError("stop failed")
    runtime._output_stream.close.side_effect = RuntimeError("close failed")
    runtime.face_tracker = MagicMock()
    runtime.face_tracker.stop.side_effect = RuntimeError("face stop failed")
    runtime.hand_tracker = MagicMock()
    runtime.hand_tracker.stop.side_effect = RuntimeError("hand stop failed")
    runtime.robot.stop_audio.side_effect = RuntimeError("audio stop failed")
    runtime.robot.disconnect.side_effect = RuntimeError("disconnect failed")
    runtime.config.motion_enabled = True
    runtime.presence.stop.side_effect = RuntimeError("presence stop failed")
    logger = SimpleNamespace(info=MagicMock())

    with patch("jarvis.runtime_lifecycle.set_runtime_voice_state") as set_voice_state:
        stop(runtime, logger=logger)

    assert runtime._started is False
    assert runtime._output_stream is None
    assert runtime.face_tracker is None
    assert runtime.hand_tracker is None
    set_voice_state.assert_called_once()
    runtime._publish_observability_status.assert_called_once()
    runtime._publish_skills_status.assert_called_once()
    logger.info.assert_called_once_with("Jarvis offline.")
