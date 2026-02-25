"""Tests for jarvis.presence — the 30Hz micro-behavior loop."""

import math
import time
import pytest
from unittest.mock import MagicMock, call

from jarvis.presence import PresenceLoop, State, Signals
from jarvis.robot.controller import RobotController, HeadPose


class TestSignals:
    def test_default_state_is_idle(self):
        s = Signals()
        assert s.state == State.IDLE
        assert s.face_detected is False
        assert s.vad_energy == 0.0
        assert s.intent_nod == 0.0

    def test_signal_mutation(self):
        s = Signals()
        s.state = State.LISTENING
        s.face_detected = True
        s.face_yaw = 15.0
        assert s.state == State.LISTENING
        assert s.face_yaw == 15.0


class TestPresenceLoop:
    def test_blend_moves_toward_target(self, presence):
        # rate=0.5 should move halfway to target
        assert presence._blend(0.0, 10.0, 0.5) == 5.0
        assert presence._blend(10.0, 0.0, 0.5) == 5.0

    def test_blend_rate_zero_stays_put(self, presence):
        assert presence._blend(5.0, 100.0, 0.0) == 5.0

    def test_blend_rate_one_jumps_to_target(self, presence):
        assert presence._blend(5.0, 100.0, 1.0) == 100.0

    def test_idle_breathing_oscillates(self, presence):
        """Idle state should produce non-zero Z (breathing) over time."""
        presence.signals.state = State.IDLE

        presence._idle_choreo_next = time.monotonic() - 0.1

        # Simulate several frames
        for _ in range(60):
            presence._do_idle(time.monotonic())

        # After many frames, Z should have moved from 0
        # (breathing oscillates, so it won't be exactly 0)
        assert presence._z != 0.0 or presence._yaw != 0.0

    def test_listening_orients_toward_face(self, presence):
        sig = presence.signals
        sig.state = State.LISTENING
        sig.face_detected = True
        sig.face_yaw = 20.0
        sig.face_pitch = 10.0
        sig.face_last_seen = time.monotonic()
        sig.vad_energy = 0.4

        # Run several frames
        for i in range(100):
            presence._do_listening(float(i) * 0.033, sig)

        # Should be moving toward the face position
        assert presence._yaw > 5.0  # should be approaching 20
        assert presence._pitch > 2.0  # should be approaching 10

    def test_turn_yield_glance_triggers_on_drop(self, presence):
        sig = presence.signals
        sig.state = State.LISTENING
        sig.face_detected = True
        sig.face_last_seen = time.monotonic()

        sig.vad_energy = 0.6
        presence._do_listening(0.0, sig)

        sig.vad_energy = 0.05
        presence._do_listening(0.2, sig)

        assert abs(presence._yaw) > 1.0

    def test_listening_loop_adds_motion(self, presence):
        sig = presence.signals
        sig.state = State.LISTENING
        sig.vad_energy = 0.05
        sig.face_detected = False

        for i in range(200):
            presence._do_listening(float(i) * 0.033, sig)

        assert abs(presence._roll) > 0.2

    def test_listening_uses_doa_when_no_face(self, presence):
        sig = presence.signals
        sig.state = State.LISTENING
        sig.face_detected = False
        sig.doa_angle = 0.0  # left side
        sig.doa_last_seen = time.monotonic()
        sig.vad_energy = 0.4

        for i in range(100):
            presence._do_listening(float(i) * 0.033, sig)

        # DoA 0 = left → should turn left (positive yaw)
        assert presence._yaw > 10.0

    def test_listening_doa_front(self, presence):
        sig = presence.signals
        sig.face_detected = False
        sig.doa_angle = math.pi / 2  # front
        sig.doa_last_seen = time.monotonic()
        sig.vad_energy = 0.4

        for i in range(100):
            presence._do_listening(float(i) * 0.033, sig)

        # Front → yaw should be near 0
        assert abs(presence._yaw) < 5.0

    def test_thinking_looks_away(self, presence):
        for i in range(100):
            presence._do_thinking(float(i) * 0.033)

        # Thinking: yaw should drift positive (look away right)
        assert presence._yaw > 5.0
        # Pitch should be slightly up
        assert presence._pitch > 0.0

    def test_speaking_returns_gaze_to_face(self, presence):
        sig = presence.signals
        sig.face_detected = True
        sig.face_yaw = 0.0
        sig.face_pitch = 0.0
        sig.face_last_seen = time.monotonic()
        sig.intent_nod = 0.0
        sig.intent_tilt = 0.0
        sig.intent_glance_yaw = 0.0
        sig.vad_energy = 0.4

        # First, look away (thinking)
        presence._yaw = 30.0
        presence._pitch = 10.0

        # Then speak — should return to face
        for i in range(100):
            presence._do_speaking(float(i) * 0.033, sig)

        assert abs(presence._yaw) < 5.0
        assert abs(presence._pitch) < 5.0

    def test_speaking_uses_hand_when_no_face(self, presence):
        sig = presence.signals
        sig.face_detected = False
        sig.hand_present = True
        sig.hand_x = 12.0
        sig.hand_y = -6.0
        sig.hand_last_seen = time.monotonic()
        sig.vad_energy = 0.4

        for i in range(100):
            presence._do_speaking(float(i) * 0.033, sig)

        assert presence._yaw > 2.0
        assert presence._pitch < -1.0

    def test_speaking_applies_intent(self, presence):
        sig = presence.signals
        sig.face_detected = False
        sig.intent_glance_yaw = 20.0
        sig.intent_tilt = 10.0
        sig.intent_nod_style = "double"

        for i in range(100):
            presence._do_speaking(float(i) * 0.033, sig)

        # Glance yaw should push yaw toward 20
        assert presence._yaw > 5.0
        # Tilt should push roll toward 10
        assert presence._roll > 2.0

    def test_speaking_sway_uses_speech_energy(self, presence):
        sig = presence.signals
        sig.face_detected = False
        sig.intent_glance_yaw = 0.0
        sig.intent_tilt = 0.0
        sig.speech_energy = 1.0

        for i in range(200):
            presence._do_speaking(float(i) * 0.033, sig)

        assert (
            abs(presence._yaw) > 0.5
            or abs(presence._pitch) > 0.5
            or abs(presence._roll) > 0.5
            or abs(presence._x) > 0.2
            or abs(presence._y) > 0.2
            or abs(presence._z) > 0.2
        )

    def test_muted_looks_down(self, presence):
        presence._yaw = 30.0
        presence._pitch = 10.0

        for _ in range(200):
            presence._do_muted()

        # Should converge to centered, looking down
        assert abs(presence._yaw) < 3.0
        assert presence._pitch < -5.0  # looking down

    def test_start_stop(self, presence):
        """Presence loop starts and stops without crashing."""
        presence.start()
        assert presence._running
        time.sleep(0.1)  # let it run a few frames
        presence.stop()
        assert not presence._running

    def test_double_start_is_safe(self, presence):
        presence.start()
        presence.start()  # should not crash or start second thread
        presence.stop()

    def test_state_transitions(self, presence):
        """All state transitions should work without errors."""
        presence.start()
        for state in State:
            presence.signals.state = state
            time.sleep(0.05)
        presence.stop()
