"""Runtime audio utility helpers for the Jarvis main loop."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    from scipy.signal import resample_poly as _resample_poly
except Exception:  # pragma: no cover - exercised via fallback path tests
    _resample_poly = None


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

    source = x.astype(np.float32, copy=False)
    if _resample_poly is not None:
        g = math.gcd(int(sr_in), int(sr_out))
        up = int(sr_out) // g
        down = int(sr_in) // g
        y = _resample_poly(source, up=up, down=down)
        return y.astype(np.float32, copy=False)

    target_len = max(1, int(round(float(source.size) * float(sr_out) / float(sr_in))))
    source_idx = np.arange(source.size, dtype=np.float32)
    target_idx = np.linspace(0.0, float(max(source.size - 1, 0)), num=target_len, dtype=np.float32)
    y = np.interp(target_idx, source_idx, source)
    return y.astype(np.float32, copy=False)
