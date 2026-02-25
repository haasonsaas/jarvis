"""Tests for jarvis.vision.face_tracker."""

import time
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from jarvis.presence import PresenceLoop, Signals
from jarvis.robot.controller import RobotController


class TestFaceTracker:
    @pytest.fixture
    def mock_presence(self):
        robot = RobotController(sim=True)
        robot.connect()
        presence = PresenceLoop(robot)
        return presence

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_detect_faces_empty(self, mock_yolo_cls, mock_presence, sample_frame):
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        # Empty results
        mock_result = MagicMock()
        mock_result.boxes = []
        mock_model.return_value = [mock_result]

        from jarvis.vision.face_tracker import FaceTracker
        tracker = FaceTracker(
            presence=mock_presence,
            get_frame=lambda: sample_frame,
        )

        detections = tracker.detect_faces(sample_frame)
        assert detections == []

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_detect_faces_single(self, mock_yolo_cls, mock_presence, sample_frame):
        import torch
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        # One detection: face at center of 640x480 frame
        mock_box = MagicMock()
        mock_box.xyxy = [torch.tensor([270.0, 190.0, 370.0, 290.0])]
        mock_box.conf = [torch.tensor(0.95)]

        mock_result = MagicMock()
        mock_result.boxes = [mock_box]
        mock_model.return_value = [mock_result]

        from jarvis.vision.face_tracker import FaceTracker
        tracker = FaceTracker(
            presence=mock_presence,
            get_frame=lambda: sample_frame,
        )

        detections = tracker.detect_faces(sample_frame)
        assert len(detections) == 1
        assert abs(detections[0].cx - 0.5) < 0.05  # center-ish
        assert abs(detections[0].cy - 0.5) < 0.05
        assert detections[0].confidence == pytest.approx(0.95, abs=0.01)

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_sorted_by_size(self, mock_yolo_cls, mock_presence, sample_frame):
        import torch
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        # Two faces: small and large
        small_box = MagicMock()
        small_box.xyxy = [torch.tensor([100.0, 100.0, 120.0, 120.0])]  # 20x20
        small_box.conf = [torch.tensor(0.8)]

        large_box = MagicMock()
        large_box.xyxy = [torch.tensor([200.0, 200.0, 400.0, 400.0])]  # 200x200
        large_box.conf = [torch.tensor(0.9)]

        mock_result = MagicMock()
        mock_result.boxes = [small_box, large_box]
        mock_model.return_value = [mock_result]

        from jarvis.vision.face_tracker import FaceTracker
        tracker = FaceTracker(
            presence=mock_presence,
            get_frame=lambda: sample_frame,
        )

        detections = tracker.detect_faces(sample_frame)
        assert len(detections) == 2
        # Largest first
        assert detections[0].w > detections[1].w

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_feeds_presence_signals(self, mock_yolo_cls, mock_presence, sample_frame):
        import torch
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model

        # Face at right side of frame
        mock_box = MagicMock()
        mock_box.xyxy = [torch.tensor([500.0, 200.0, 600.0, 300.0])]
        mock_box.conf = [torch.tensor(0.9)]
        mock_result = MagicMock()
        mock_result.boxes = [mock_box]
        mock_model.return_value = [mock_result]

        from jarvis.vision.face_tracker import FaceTracker
        tracker = FaceTracker(
            presence=mock_presence,
            get_frame=lambda: sample_frame,
            fps=100,  # fast for testing
        )

        # Run the tracker briefly
        tracker.start()
        time.sleep(0.2)
        tracker.stop()

        # Should have set face_detected and face position
        assert mock_presence.signals.face_detected is True

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_no_face_clears_signal(self, mock_yolo_cls, mock_presence):
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model
        mock_result = MagicMock()
        mock_result.boxes = []
        mock_model.return_value = [mock_result]

        from jarvis.vision.face_tracker import FaceTracker

        # get_frame returns None -> face_detected should be False
        tracker = FaceTracker(
            presence=mock_presence,
            get_frame=lambda: None,
            fps=100,
        )
        tracker.start()
        time.sleep(0.1)
        tracker.stop()

        assert mock_presence.signals.face_detected is False

    @patch("jarvis.vision.face_tracker.YOLO")
    def test_start_stop(self, mock_yolo_cls, mock_presence):
        mock_yolo_cls.return_value = MagicMock()

        from jarvis.vision.face_tracker import FaceTracker
        tracker = FaceTracker(
            presence=mock_presence,
            get_frame=lambda: None,
        )

        tracker.start()
        assert tracker._running
        tracker.stop()
        assert not tracker._running
