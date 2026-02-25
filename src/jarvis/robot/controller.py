"""Wrapper around Reachy Mini SDK for robot control."""

from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass

from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose
from reachy_mini.motion.recorded_move import RecordedMoves

log = logging.getLogger(__name__)

EMOTIONS_REPO = "pollen-robotics/reachy-mini-emotions-library"
DANCES_REPO = "pollen-robotics/reachy-mini-dances-library"

# Conservative safety limits (degrees / mm) to avoid mechanical extremes.
HEAD_LIMITS = {
    "x": (-10.0, 10.0),
    "y": (-10.0, 10.0),
    "z": (-10.0, 10.0),
    "roll": (-20.0, 20.0),
    "pitch": (-25.0, 25.0),
    "yaw": (-50.0, 50.0),
}


@dataclass
class HeadPose:
    """Head position in degrees and mm."""
    x: float = 0.0   # forward/back (mm)
    y: float = 0.0   # left/right (mm)
    z: float = 0.0   # up/down (mm)
    roll: float = 0.0   # tilt (degrees)
    pitch: float = 0.0  # nod (degrees)
    yaw: float = 0.0    # turn (degrees)


class RobotController:
    """High-level controller for Reachy Mini."""

    def __init__(
        self,
        host: str | None = None,
        sim: bool = False,
        connection_mode: str | None = None,
        media_backend: str | None = None,
    ):
        self._host = host
        self._sim = sim
        self._connection_mode = connection_mode
        self._media_backend = media_backend
        self._mini: ReachyMini | None = None
        self._emotions: RecordedMoves | None = None
        self._dances: RecordedMoves | None = None
        self._connected = False

        self._recording_started = False
        self._playing_started = False

    @property
    def sim(self) -> bool:
        return self._sim

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if self._sim:
            log.info("Running in simulation mode — no robot connected")
            return
        try:
            kwargs: dict[str, object] = {}
            if self._host:
                kwargs["host"] = self._host
            if self._connection_mode:
                kwargs["connection_mode"] = self._connection_mode
            if self._media_backend:
                kwargs["media_backend"] = self._media_backend

            try:
                self._mini = ReachyMini(**kwargs) if kwargs else ReachyMini()
            except TypeError:
                # Backward/forward compatibility with SDK constructor kwargs.
                self._mini = ReachyMini()

            self._mini.__enter__()
            self._connected = True
            log.info("Connected to Reachy Mini")
        except Exception as e:
            log.error("Failed to connect to Reachy Mini: %s", e)
            log.info("Falling back to simulation mode")
            self._mini = None
            self._sim = True
            return

        # Pre-load emotion and dance libraries
        try:
            self._emotions = RecordedMoves(EMOTIONS_REPO)
            log.info("Loaded emotions library")
        except Exception as e:
            log.warning("Could not load emotions library: %s", e)

        try:
            self._dances = RecordedMoves(DANCES_REPO)
            log.info("Loaded dances library")
        except Exception as e:
            log.warning("Could not load dances library: %s", e)

    def disconnect(self) -> None:
        if self._mini and self._connected:
            try:
                self.stop_audio(recording=True, playing=True)
                self._mini.__exit__(None, None, None)
            except Exception as e:
                log.warning("Error during disconnect: %s", e)
            finally:
                self._mini = None
                self._connected = False
                log.info("Disconnected from Reachy Mini")

    def _clamp_pose(self, pose: HeadPose) -> HeadPose:
        return HeadPose(
            x=max(HEAD_LIMITS["x"][0], min(HEAD_LIMITS["x"][1], pose.x)),
            y=max(HEAD_LIMITS["y"][0], min(HEAD_LIMITS["y"][1], pose.y)),
            z=max(HEAD_LIMITS["z"][0], min(HEAD_LIMITS["z"][1], pose.z)),
            roll=max(HEAD_LIMITS["roll"][0], min(HEAD_LIMITS["roll"][1], pose.roll)),
            pitch=max(HEAD_LIMITS["pitch"][0], min(HEAD_LIMITS["pitch"][1], pose.pitch)),
            yaw=max(HEAD_LIMITS["yaw"][0], min(HEAD_LIMITS["yaw"][1], pose.yaw)),
        )

    # ── Movement ──────────────────────────────────────────────

    def move_head(self, pose: HeadPose, duration: float = 1.0) -> None:
        """Smooth head movement to target pose."""
        if not self._mini:
            log.debug("SIM: move_head %s", pose)
            return
        pose = self._clamp_pose(pose)
        head = create_head_pose(
            x=pose.x, y=pose.y, z=pose.z,
            roll=pose.roll, pitch=pose.pitch, yaw=pose.yaw,
            degrees=True, mm=True,
        )
        self._mini.goto_target(head=head, duration=max(0.1, duration))

    def set_head_realtime(self, pose: HeadPose) -> None:
        """Instant head position update for tracking loops."""
        if not self._mini:
            return
        pose = self._clamp_pose(pose)
        head = create_head_pose(
            x=pose.x, y=pose.y, z=pose.z,
            roll=pose.roll, pitch=pose.pitch, yaw=pose.yaw,
            degrees=True, mm=True,
        )
        self._mini.set_target(head=head)

    def turn_body(self, yaw_degrees: float, duration: float = 1.0) -> None:
        """Rotate body to given yaw angle."""
        if not self._mini:
            log.debug("SIM: turn_body yaw=%.1f", yaw_degrees)
            return
        yaw_clamped = max(-160.0, min(160.0, yaw_degrees))
        self._mini.goto_target(
            body_yaw=np.deg2rad(yaw_clamped),
            duration=max(0.1, duration),
        )

    def set_antennas(self, left: float = 0.0, right: float = 0.0, duration: float = 0.5) -> None:
        """Set antenna positions in degrees."""
        if not self._mini:
            return
        self._mini.goto_target(
            antennas=np.deg2rad([left, right]),
            duration=max(0.1, duration),
        )

    # ── Expressions ───────────────────────────────────────────

    def play_emotion(self, name: str) -> None:
        """Play a pre-recorded emotion animation."""
        if not self._mini or not self._emotions:
            log.debug("SIM: play_emotion %s", name)
            return
        move = self._emotions.get(name)
        if move:
            self._mini.play_move(move, initial_goto_duration=0.5)
        else:
            log.warning("Unknown emotion: %s (available: %s)", name, self.list_emotions())

    def play_dance(self, name: str) -> None:
        """Play a pre-recorded dance."""
        if not self._mini or not self._dances:
            log.debug("SIM: play_dance %s", name)
            return
        move = self._dances.get(name)
        if move:
            self._mini.play_move(move, initial_goto_duration=1.0)
        else:
            log.warning("Unknown dance: %s (available: %s)", name, self.list_dances())

    def list_emotions(self) -> list[str]:
        if self._emotions:
            return list(self._emotions.list_moves())
        return []

    def list_dances(self) -> list[str]:
        if self._dances:
            return list(self._dances.list_moves())
        return []

    # ── Camera ────────────────────────────────────────────────

    def get_frame(self) -> np.ndarray | None:
        """Get current camera frame as numpy array (H, W, 3)."""
        if not self._mini:
            return None
        try:
            return self._mini.media.get_frame()
        except Exception as e:
            log.debug("Failed to get frame: %s", e)
            return None

    # ── Audio (Reachy Mini media) ───────────────────────────

    def start_audio(self, recording: bool = True, playing: bool = True) -> None:
        """Reserve and start Reachy Mini audio devices via the SDK media API."""
        if not self._mini:
            return
        try:
            if recording and not self._recording_started:
                self._mini.media.start_recording()
                self._recording_started = True
            if playing and not self._playing_started:
                self._mini.media.start_playing()
                self._playing_started = True
        except Exception as e:
            log.warning("Failed to start Reachy Mini audio: %s", e)

    def stop_audio(self, recording: bool = True, playing: bool = True) -> None:
        if not self._mini:
            return

        if recording and self._recording_started:
            try:
                self._mini.media.stop_recording()
            except Exception as e:
                log.debug("Failed to stop recording: %s", e)
            finally:
                self._recording_started = False

        if playing and self._playing_started:
            try:
                self._mini.media.stop_playing()
            except Exception as e:
                log.debug("Failed to stop playing: %s", e)
            finally:
                self._playing_started = False

    def flush_audio_output(self) -> None:
        """Best-effort stop/clear any queued audio output."""
        if not self._mini or not self._playing_started:
            return

        try:
            media = self._mini.media
            audio = getattr(media, "audio", None)

            # Prefer backend-specific flush when available.
            if audio is not None:
                if hasattr(audio, "clear_player"):
                    audio.clear_player()  # type: ignore[attr-defined]
                    return
                if hasattr(audio, "clear_output_buffer"):
                    audio.clear_output_buffer()  # type: ignore[attr-defined]
                    return

            # Fallback: restart the playing pipeline.
            media.stop_playing()
            media.start_playing()
        except Exception as e:
            log.debug("Failed to flush audio output: %s", e)

    def get_input_audio_samplerate(self) -> int | None:
        if not self._mini:
            return None
        try:
            sr = int(self._mini.media.get_input_audio_samplerate())
            return sr if sr > 0 else None
        except Exception:
            return None

    def get_output_audio_samplerate(self) -> int | None:
        if not self._mini:
            return None
        try:
            sr = int(self._mini.media.get_output_audio_samplerate())
            return sr if sr > 0 else None
        except Exception:
            return None

    def get_audio_sample(self) -> np.ndarray | None:
        """Get a chunk of microphone audio (float32)."""
        if not self._mini or not self._recording_started:
            return None
        try:
            return self._mini.media.get_audio_sample()
        except Exception as e:
            log.debug("Failed to get audio sample: %s", e)
            return None

    def push_audio_sample(self, samples: np.ndarray) -> None:
        """Push a chunk of audio to the speaker (non-blocking)."""
        if not self._mini or not self._playing_started:
            return
        try:
            if samples.ndim == 1:
                samples = samples.reshape(-1, 1)
            self._mini.media.push_audio_sample(samples)
        except Exception as e:
            log.debug("Failed to push audio sample: %s", e)

    def get_doa(self) -> tuple[float | None, bool | None]:
        """Direction of Arrival (radians) and speech detection flag, if available."""
        if not self._mini:
            return None, None
        try:
            doa, is_speech = self._mini.media.get_DoA()
            return float(doa), bool(is_speech)
        except Exception:
            return None, None
