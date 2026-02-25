"""Presence loop — the always-running soul of Jarvis.

This runs independently of the LLM at ~30Hz and makes the robot feel alive.
It takes lightweight signals and maps them to continuous micro-behaviors:

  - IDLE: slow breathing motion, occasional tiny attention shifts
  - LISTENING: orient toward DoA, micro-nods, subtle lean forward
  - THINKING: look away slightly, processing animation
  - SPEAKING: stable gaze at user, minimal jitter
  - MUTED: privacy posture (centered, looks slightly down)

The LLM never touches this loop directly. It just sets signals.
"""

from __future__ import annotations

import enum
import logging
import math
import threading
import time
from dataclasses import dataclass, field

from jarvis.robot.controller import RobotController, HeadPose

log = logging.getLogger(__name__)

LOOP_HZ = 30
LOOP_INTERVAL = 1.0 / LOOP_HZ


class State(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    MUTED = "muted"


@dataclass
class Signals:
    """Lightweight signals fed into the presence loop from other systems.

    Written by: main thread (state, vad_energy), face tracker thread (face_*),
    audio thread (doa_angle), brain (intent_*).
    Read by: presence loop thread.

    Individual float/bool writes are atomic on CPython (GIL), so we don't
    need locks for this dataclass — torn reads aren't possible for single
    primitive fields.
    """
    state: State = State.IDLE
    doa_angle: float | None = None       # Direction of arrival (radians, None = unknown)
    vad_energy: float = 0.0              # 0-1 speech energy level
    face_yaw: float = 0.0               # Face tracker's suggested yaw (degrees)
    face_pitch: float = 0.0             # Face tracker's suggested pitch (degrees)
    face_detected: bool = False
    # Set by the embodiment plan from the LLM
    intent_nod: float = 0.0             # 0-1 nod intensity
    intent_tilt: float = 0.0            # degrees of head tilt
    intent_glance_yaw: float = 0.0      # brief glance offset
    speech_energy: float = 0.0          # 0-1 TTS energy for speech sway


class PresenceLoop:
    """Real-time micro-behavior controller.

    Runs in its own thread at 30Hz. Other systems set signals,
    this loop blends them into continuous robot motion.
    """

    def __init__(self, robot: RobotController):
        self._robot = robot
        self.signals = Signals()
        self._running = False
        self._thread: threading.Thread | None = None
        self._t0 = 0.0

        # Smoothed outputs
        self._yaw = 0.0
        self._pitch = 0.0
        self._roll = 0.0
        self._z = 0.0  # head height
        self._antenna_left = 0.0
        self._antenna_right = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="presence")
        self._thread.start()
        log.info("Presence loop started at %dHz", LOOP_HZ)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                log.warning("Presence loop thread did not stop within timeout")
            self._thread = None
        log.info("Presence loop stopped")

    def _loop(self) -> None:
        while self._running:
            t = time.monotonic()
            elapsed = t - self._t0
            dt = LOOP_INTERVAL  # use fixed dt for consistent smoothing
            sig = self.signals

            match sig.state:
                case State.IDLE:
                    self._do_idle(elapsed)
                case State.LISTENING:
                    self._do_listening(elapsed, sig)
                case State.THINKING:
                    self._do_thinking(elapsed)
                case State.SPEAKING:
                    self._do_speaking(elapsed, sig)
                case State.MUTED:
                    self._do_muted()

            # Apply smoothed pose
            self._robot.set_head_realtime(HeadPose(
                yaw=self._yaw,
                pitch=self._pitch,
                roll=self._roll,
                z=self._z,
            ))

            self._update_antennas(elapsed, sig)

            # Maintain loop rate
            actual_dt = time.monotonic() - t
            if actual_dt < LOOP_INTERVAL:
                time.sleep(LOOP_INTERVAL - actual_dt)

    def _blend(self, current: float, target: float, rate: float = 0.1) -> float:
        """Exponential smoothing toward target. Rate = weight on NEW value."""
        return current + (target - current) * rate

    def _clamp(self, value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    # ── State behaviors ──────────────────────────────────────

    def _do_idle(self, t: float) -> None:
        # Slow breathing: subtle up/down + slight roll oscillation
        breath = math.sin(t * 0.8) * 2.0  # ±2mm Z
        drift_yaw = math.sin(t * 0.15) * 3.0  # slow wandering gaze
        drift_roll = math.sin(t * 0.3) * 1.5

        self._z = self._blend(self._z, breath)
        self._yaw = self._blend(self._yaw, drift_yaw, 0.03)
        self._pitch = self._blend(self._pitch, -2.0, 0.03)  # slight downward rest
        self._roll = self._blend(self._roll, drift_roll, 0.03)

    def _do_listening(self, t: float, sig: Signals) -> None:
        # Orient toward speaker (face tracker or DoA)
        if sig.face_detected:
            target_yaw = sig.face_yaw
            target_pitch = sig.face_pitch
        elif sig.doa_angle is not None:
            # DoA: 0=left, pi/2=front, pi=right → map to yaw degrees
            # Clamp to expected range before mapping
            angle = max(0.0, min(math.pi, sig.doa_angle))
            target_yaw = -((angle - math.pi / 2) / (math.pi / 2)) * 40.0
            target_pitch = 0.0
        else:
            target_yaw = 0.0
            target_pitch = 0.0

        # Lean forward slightly when listening
        lean = 2.0
        # Micro-nods correlated with VAD energy
        nod = math.sin(t * 4.0) * sig.vad_energy * 3.0

        target_yaw = self._clamp(target_yaw, -45.0, 45.0)
        target_pitch = self._clamp(target_pitch + nod, -20.0, 20.0)
        self._yaw = self._blend(self._yaw, target_yaw, 0.15)
        self._pitch = self._blend(self._pitch, target_pitch, 0.15)
        self._z = self._blend(self._z, lean, 0.1)
        self._roll = self._blend(self._roll, 0.0, 0.1)

    def _do_thinking(self, t: float) -> None:
        # Look slightly away and up — the "pondering" pose
        think_yaw = 15.0 + math.sin(t * 0.5) * 5.0
        think_pitch = 5.0 + math.sin(t * 0.7) * 2.0
        think_roll = math.sin(t * 0.4) * 3.0

        self._yaw = self._blend(self._yaw, think_yaw, 0.08)
        self._pitch = self._blend(self._pitch, think_pitch, 0.08)
        self._roll = self._blend(self._roll, think_roll, 0.05)
        self._z = self._blend(self._z, 0.0, 0.05)

    def _do_speaking(self, t: float, sig: Signals) -> None:
        # Return gaze to user, stable with subtle animation
        if sig.face_detected:
            target_yaw = sig.face_yaw
            target_pitch = sig.face_pitch
        else:
            target_yaw = 0.0
            target_pitch = 0.0

        # Add any LLM-requested intent
        target_yaw += sig.intent_glance_yaw
        target_pitch += sig.intent_nod * math.sin(t * 3.0) * 4.0
        target_roll = sig.intent_tilt

        sway = sig.speech_energy
        target_yaw += math.sin(t * 0.6) * 4.0 * sway
        target_pitch += math.sin(t * 2.0) * 2.0 * sway
        target_roll += math.sin(t * 1.2) * 1.5 * sway

        target_yaw = self._clamp(target_yaw, -45.0, 45.0)
        target_pitch = self._clamp(target_pitch, -20.0, 20.0)
        target_roll = self._clamp(target_roll, -15.0, 15.0)

        self._yaw = self._blend(self._yaw, target_yaw, 0.12)
        self._pitch = self._blend(self._pitch, target_pitch, 0.12)
        self._roll = self._blend(self._roll, target_roll, 0.08)
        self._z = self._blend(self._z, 1.0, 0.05)  # slight upward "engaged" posture

    def _do_muted(self) -> None:
        # Privacy posture: centered, looking slightly down
        self._yaw = self._blend(self._yaw, 0.0, 0.05)
        self._pitch = self._blend(self._pitch, -10.0, 0.05)
        self._roll = self._blend(self._roll, 0.0, 0.05)
        self._z = self._blend(self._z, -3.0, 0.05)

    def _update_antennas(self, t: float, sig: Signals) -> None:
        if sig.state == State.IDLE:
            wave = math.sin(t * 0.6) * 8.0
            target_left = wave
            target_right = -wave
        elif sig.state == State.LISTENING:
            target_left = 0.0
            target_right = 0.0
        elif sig.state == State.THINKING:
            target_left = 5.0
            target_right = 5.0
        elif sig.state == State.SPEAKING:
            wave = math.sin(t * 1.2) * 4.0
            target_left = wave
            target_right = wave
        else:  # MUTED
            target_left = -8.0
            target_right = -8.0

        self._antenna_left = self._blend(self._antenna_left, target_left, 0.1)
        self._antenna_right = self._blend(self._antenna_right, target_right, 0.1)
        self._robot.set_antennas_realtime(self._antenna_left, self._antenna_right)
