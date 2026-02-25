"""Tests for jarvis.robot.controller."""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from jarvis.robot.controller import RobotController, HeadPose, MotionStep


class TestHeadPose:
    def test_defaults(self):
        p = HeadPose()
        assert p.x == 0.0
        assert p.yaw == 0.0

    def test_keyword_args(self):
        p = HeadPose(yaw=30.0, pitch=-10.0, z=5.0)
        assert p.yaw == 30.0
        assert p.pitch == -10.0
        assert p.z == 5.0


class TestRobotControllerSim:
    """Tests with sim=True — no real robot needed."""

    def test_sim_connect(self, mock_robot):
        # Should not crash
        assert mock_robot._sim is True

    def test_move_head_in_sim(self, mock_robot):
        # Should not crash, just log
        mock_robot.move_head(HeadPose(yaw=30.0))

    def test_set_head_realtime_in_sim(self, mock_robot):
        mock_robot.set_head_realtime(HeadPose(pitch=10.0))

    def test_turn_body_in_sim(self, mock_robot):
        mock_robot.turn_body(45.0)

    def test_set_antennas_in_sim(self, mock_robot):
        mock_robot.set_antennas(left=30.0, right=30.0)

    def test_play_emotion_in_sim(self, mock_robot):
        mock_robot.play_emotion("happy")

    def test_play_dance_in_sim(self, mock_robot):
        mock_robot.play_dance("groove")

    def test_list_emotions_empty_in_sim(self, mock_robot):
        assert mock_robot.list_emotions() == []

    def test_list_dances_empty_in_sim(self, mock_robot):
        assert mock_robot.list_dances() == []

    def test_get_frame_none_in_sim(self, mock_robot):
        assert mock_robot.get_frame() is None

    def test_disconnect_in_sim(self, mock_robot):
        mock_robot.disconnect()  # should not crash


class TestRobotControllerReal:
    """Tests with mocked ReachyMini SDK."""

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_connect_success(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()

        mock_mini.__enter__.assert_called_once()
        assert rc._connected is True

    @patch("jarvis.robot.controller.ReachyMini")
    def test_connect_failure_falls_back_to_sim(self, mock_mini_cls):
        mock_mini_cls.side_effect = ConnectionError("Robot not found")

        rc = RobotController(sim=False)
        rc.connect()

        assert rc._sim is True
        assert rc._mini is None

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_disconnect(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()
        rc.disconnect()

        mock_mini.__exit__.assert_called_once_with(None, None, None)
        assert rc._connected is False

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_run_sequence_calls_goto_target(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()
        rc.run_sequence([
            MotionStep(kind="head", pose=HeadPose(yaw=10.0), duration=0.2),
            MotionStep(kind="body", body_yaw=15.0, duration=0.2),
        ], blocking=True)

        assert mock_mini.goto_target.call_count >= 2

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_run_macro_acknowledge(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()
        rc.run_macro("acknowledge", intensity=1.0, blocking=True)

        assert mock_mini.goto_target.call_count >= 1

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_move_head_calls_goto_target(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()
        rc.move_head(HeadPose(yaw=30.0), duration=1.5)

        mock_mini.goto_target.assert_called_once()

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_move_head_clamps_duration(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()
        rc.move_head(HeadPose(), duration=-1.0)

        # Duration should be clamped to 0.1
        call_kwargs = mock_mini.goto_target.call_args
        assert call_kwargs.kwargs.get("duration", call_kwargs[1].get("duration")) >= 0.1

    @patch("jarvis.robot.controller.ReachyMini")
    @patch("jarvis.robot.controller.RecordedMoves")
    def test_turn_body_clamps_yaw(self, mock_moves_cls, mock_mini_cls):
        mock_mini = MagicMock()
        mock_mini_cls.return_value = mock_mini

        rc = RobotController(sim=False)
        rc.connect()
        rc.turn_body(999.0)  # way out of range

        # Should have been clamped
        call_args = mock_mini.goto_target.call_args
        body_yaw = call_args.kwargs.get("body_yaw", call_args[1].get("body_yaw"))
        assert body_yaw <= np.deg2rad(160.0)
