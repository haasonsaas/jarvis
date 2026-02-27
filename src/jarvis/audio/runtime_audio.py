"""Runtime audio utility helpers for the Jarvis main loop."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.signal import resample_poly


def require_sounddevice(sd_obj: Any, import_error: str | None, *, feature: str) -> None:
    if sd_obj is not None:
        return
    detail = f" ({import_error})" if import_error else ""
    raise RuntimeError(f"sounddevice is unavailable; {feature} requires PortAudio.{detail}")


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert arbitrary audio frame to 1D float32 mono."""
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim == 1:
        return a
    if a.ndim != 2:
        return a.reshape(-1).astype(np.float32, copy=False)

    # Heuristic: if channels appear first, transpose.
    if a.shape[0] <= 8 and a.shape[0] < a.shape[1]:
        a = a.T

    if a.shape[1] == 1:
        return a[:, 0]
    return a.mean(axis=1)


def resample_audio(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or x.size == 0:
        return x.astype(np.float32, copy=False)

    g = math.gcd(int(sr_in), int(sr_out))
    up = int(sr_out) // g
    down = int(sr_in) // g
    y = resample_poly(x.astype(np.float32, copy=False), up=up, down=down)
    return y.astype(np.float32, copy=False)
