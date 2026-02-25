"""
Lightweight hand tracking (heuristic) to drive presence signals.
Uses a simple bright-region detector to avoid heavy dependencies.
"""

from __future__ import annotations

import logging
import time
import threading
import numpy as np
from dataclasses import dataclass

from jarvis.presence import PresenceLoop

log = logging.getLogger(__name__)

# Frame center (normalized 0-1)
FRAME_CX, FRAME_CY = 0.5, 0.5

# Degrees per unit of offset from center
GAIN_YAW = 35.0
GAIN_PITCH = 25.0

MIN_BRIGHTNESS = 200  # 0-255 threshold for a bright blob
MIN_AREA_RATIO = 0.005  # blob must cover at least this fraction of frame
SMOOTH_ALPHA = 0.2


@dataclass
class HandDetection:
    cx: float
    cy: float
    area_ratio: float


class HandTracker:
    """Finds a bright hand-like blob and feeds presence loop signals."""

    def __init__(self, presence: PresenceLoop, get_frame, fps: int = 10):
        self._presence = presence
        self._get_frame = get_frame
        self._interval = 1.0 / fps
        self._running = False
        self._thread: threading.Thread | None = None

        self._smooth_yaw = 0.0
        self._smooth_pitch = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hand-tracker")
        self._thread.start()
        log.info("Hand tracking started at %dHz", int(1.0 / self._interval))

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                log.warning("Hand tracker thread did not stop within timeout")
            self._thread = None
        log.info("Hand tracking stopped")

    def detect_hand(self, frame: np.ndarray) -> HandDetection | None:
        if frame.size == 0:
            return None
        h, w = frame.shape[:2]
        gray = frame
        if frame.ndim == 3:
            gray = frame.mean(axis=2)
        mask = gray >= MIN_BRIGHTNESS
        if not np.any(mask):
            return None
        ys, xs = np.nonzero(mask)
        area_ratio = float(len(xs)) / float(h * w)
        if area_ratio < MIN_AREA_RATIO:
            return None
        cx = float(xs.mean()) / float(w)
        cy = float(ys.mean()) / float(h)
        return HandDetection(cx=cx, cy=cy, area_ratio=area_ratio)

    def _loop(self) -> None:
        while self._running:
            t0 = time.monotonic()
            frame = self._get_frame()
            if frame is None:
                self._presence.signals.hand_present = False
                time.sleep(self._interval)
                continue

            try:
                detection = self.detect_hand(frame)
            except Exception as e:
                log.debug("Hand detection error: %s", e)
                detection = None

            if detection:
                err_x = FRAME_CX - detection.cx
                err_y = FRAME_CY - detection.cy
                raw_yaw = err_x * GAIN_YAW
                raw_pitch = err_y * GAIN_PITCH
                self._smooth_yaw += SMOOTH_ALPHA * (raw_yaw - self._smooth_yaw)
                self._smooth_pitch += SMOOTH_ALPHA * (raw_pitch - self._smooth_pitch)

                self._presence.signals.hand_present = True
                self._presence.signals.hand_x = self._smooth_yaw
                self._presence.signals.hand_y = self._smooth_pitch
                self._presence.signals.hand_last_seen = time.monotonic()
            else:
                self._presence.signals.hand_present = False

            elapsed = time.monotonic() - t0
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
