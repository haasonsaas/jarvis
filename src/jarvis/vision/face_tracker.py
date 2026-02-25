"""YOLOv8-based face detection and tracking for Reachy Mini.

Feeds face position into the presence loop signals rather than
controlling the robot head directly — the presence loop blends
face tracking with other behaviors (breathing, listening, etc.).
"""

from __future__ import annotations

import logging
import math
import time
import threading
import numpy as np
from dataclasses import dataclass

from ultralytics import YOLO

from jarvis.presence import PresenceLoop

log = logging.getLogger(__name__)

# Frame center (normalized 0-1)
FRAME_CX, FRAME_CY = 0.5, 0.4  # slightly above center for typical face position

# Degrees of head movement per unit of offset from center
GAIN_YAW = 50.0
GAIN_PITCH = 35.0

# Smoothing: 0 = instant (jittery), 1 = frozen. 0.3 = responsive with mild smoothing
SMOOTH_ALPHA = 0.3


@dataclass
class Detection:
    """A detected face with bounding box center (normalized 0-1)."""
    cx: float
    cy: float
    w: float
    h: float
    confidence: float


class FaceTracker:
    """Detects faces with YOLOv8 and feeds position into the presence loop.

    Uses a face-specific model (yolov8n-face.pt) for direct face detection,
    avoiding the person-bbox-to-face heuristic.
    """

    def __init__(self, presence: PresenceLoop, get_frame, model_path: str = "yolov8n-face.pt", fps: int = 10):
        """
        Args:
            presence: The presence loop to feed face signals into.
            get_frame: Callable that returns a camera frame (H, W, 3) ndarray or None.
            model_path: Path to YOLOv8 model. Use a face-specific model for best results.
            fps: Target detection frequency.
        """
        self._presence = presence
        self._get_frame = get_frame
        self._model = YOLO(model_path)
        self._interval = 1.0 / fps
        self._running = False
        self._thread: threading.Thread | None = None

        # Smoothed output
        self._smooth_yaw = 0.0
        self._smooth_pitch = 0.0

    def start(self) -> None:
        """Start the face tracking loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="face-tracker")
        self._thread.start()
        log.info("Face tracking started at %dHz", int(1.0 / self._interval))

    def stop(self) -> None:
        """Stop the face tracking loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                log.warning("Face tracker thread did not stop within timeout")
            self._thread = None
        log.info("Face tracking stopped")

    def detect_faces(self, frame: np.ndarray) -> list[Detection]:
        """Run YOLOv8 on a frame and return face detections."""
        results = self._model(frame, verbose=False)

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                h_frame, w_frame = frame.shape[:2]

                detections.append(Detection(
                    cx=float(((x1 + x2) / 2) / w_frame),
                    cy=float(((y1 + y2) / 2) / h_frame),
                    w=float((x2 - x1) / w_frame),
                    h=float((y2 - y1) / h_frame),
                    confidence=float(box.conf[0]),
                ))

        # Sort by size (closest face first)
        detections.sort(key=lambda d: d.w * d.h, reverse=True)
        return detections

    def _loop(self) -> None:
        """Main tracking loop — runs in background thread."""
        while self._running:
            t0 = time.monotonic()

            frame = self._get_frame()
            if frame is None:
                self._presence.signals.face_detected = False
                time.sleep(self._interval)
                continue

            try:
                detections = self.detect_faces(frame)
            except Exception as e:
                log.debug("Detection error: %s", e)
                time.sleep(self._interval)
                continue

            if detections:
                face = detections[0]
                # Compute error from frame center
                err_x = FRAME_CX - face.cx   # positive = face is to the left of center
                err_y = FRAME_CY - face.cy   # positive = face is above center

                raw_yaw = err_x * GAIN_YAW
                raw_pitch = err_y * GAIN_PITCH

                # Exponential smoothing — SMOOTH_ALPHA is the weight on NEW values
                self._smooth_yaw += SMOOTH_ALPHA * (raw_yaw - self._smooth_yaw)
                self._smooth_pitch += SMOOTH_ALPHA * (raw_pitch - self._smooth_pitch)

                # Feed into presence loop signals (not robot directly)
                self._presence.signals.face_detected = True
                self._presence.signals.face_yaw = self._smooth_yaw
                self._presence.signals.face_pitch = self._smooth_pitch
            else:
                self._presence.signals.face_detected = False

            # Maintain target FPS
            elapsed = time.monotonic() - t0
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
