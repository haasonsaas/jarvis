import time
import numpy as np
from unittest.mock import MagicMock

from jarvis.presence import PresenceLoop
from jarvis.robot.controller import RobotController
from jarvis.vision.hand_tracker import HandTracker


def test_detect_hand_returns_none_when_dark():
    robot = RobotController(sim=True)
    robot.connect()
    presence = PresenceLoop(robot)
    tracker = HandTracker(presence=presence, get_frame=lambda: None)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert tracker.detect_hand(frame) is None


def test_detect_hand_finds_bright_blob():
    robot = RobotController(sim=True)
    robot.connect()
    presence = PresenceLoop(robot)
    tracker = HandTracker(presence=presence, get_frame=lambda: None)

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[30:60, 40:70] = 255
    detection = tracker.detect_hand(frame)
    assert detection is not None
    assert 0.3 < detection.cx < 0.8
    assert 0.3 < detection.cy < 0.8


def test_loop_updates_presence_signals():
    robot = RobotController(sim=True)
    robot.connect()
    presence = PresenceLoop(robot)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[20:50, 60:90] = 255
    tracker = HandTracker(presence=presence, get_frame=lambda: frame, fps=100)

    tracker.start()
    time.sleep(0.1)
    tracker.stop()

    assert presence.signals.hand_present is True
