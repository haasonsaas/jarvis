"""Integration tests — verify subsystems work together.

These test the wiring between components using mocks for external
dependencies (hardware, APIs) but real internal logic.
"""

import time
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock

from jarvis.presence import PresenceLoop, State
from jarvis.robot.controller import RobotController, HeadPose


class TestPresenceWithFaceTracker:
    """Test that face tracker feeds into presence loop correctly."""

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_face_tracker_drives_presence(self, mock_yolo_cls):
        import torch

        robot = RobotController(sim=True)
        robot.connect()
        presence = PresenceLoop(robot)

        # Setup YOLO to detect a face on the left
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        mock_box = MagicMock()
        mock_box.xyxy = [torch.tensor([50.0, 200.0, 150.0, 300.0])]  # left side
        mock_box.conf = [torch.tensor(0.9)]
        mock_result = MagicMock()
        mock_result.boxes = [mock_box]
        mock_model.return_value = [mock_result]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        from jarvis.vision.face_tracker import FaceTracker
        tracker = FaceTracker(
            presence=presence,
            get_frame=lambda: frame,
            fps=50,
        )

        presence.signals.state = State.LISTENING
        presence.start()
        tracker.start()
        time.sleep(0.3)
        tracker.stop()
        presence.stop()

        # Face was on the left -> tracker should have produced recent face signals.
        assert presence.signals.face_last_seen is not None


class TestPresenceStateTransitions:
    """Test that presence loop handles rapid state changes."""

    def test_rapid_state_cycling(self, mock_robot):
        presence = PresenceLoop(mock_robot)
        presence.start()

        # Rapidly cycle through states
        for _ in range(5):
            for state in State:
                presence.signals.state = state
                time.sleep(0.02)

        presence.stop()
        # Should not crash or deadlock


class TestEmbodyIntegration:
    """Test that embody tool properly affects presence loop behavior."""

    def test_nod_affects_speaking_state(self, mock_robot):
        from jarvis.tools.robot import bind, embody
        import asyncio

        presence = PresenceLoop(mock_robot)
        bind(mock_robot, presence)

        # Set speaking state with nod
        presence.signals.state = State.SPEAKING
        presence.signals.intent_nod = 0.8

        # Run a few frames
        for i in range(50):
            presence._do_speaking(float(i) * 0.033, presence.signals)

        # Pitch should be oscillating (nod effect)
        # Just verify it's not stuck at 0
        assert presence._pitch != 0.0 or presence._roll != 0.0


class TestAudioPipelineFlow:
    """Test audio pipeline data flow with mocked components."""

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    @patch("jarvis.audio.stt.WhisperModel")
    def test_vad_to_stt_flow(self, mock_whisper_cls, mock_vad_iter, mock_load_vad):
        import torch

        # Setup VAD to detect speech
        mock_model = MagicMock()
        mock_model.return_value = torch.tensor(0.9)
        mock_load_vad.return_value = mock_model

        # Setup STT
        mock_whisper = MagicMock()
        seg = MagicMock()
        seg.text = "hello jarvis"
        mock_whisper.transcribe.return_value = (iter([seg]), MagicMock())
        mock_whisper_cls.return_value = mock_whisper

        from jarvis.audio.vad import VoiceActivityDetector
        from jarvis.audio.stt import SpeechToText

        vad = VoiceActivityDetector()
        stt = SpeechToText()

        # Simulate: VAD detects speech in 10 chunks, then silence
        chunks = []
        for _ in range(10):
            chunk = np.random.randn(512).astype(np.float32) * 0.1
            if vad.is_speech(chunk):
                chunks.append(chunk)

        # Concatenate and transcribe
        if chunks:
            audio = np.concatenate(chunks)
            text = stt.transcribe(audio)
            assert text == "hello jarvis"
