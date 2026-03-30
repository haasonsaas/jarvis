"""Tests for audio runtime utility helpers."""

from __future__ import annotations

import numpy as np

from jarvis.audio import runtime_audio


def test_resample_audio_falls_back_without_scipy() -> None:
    source = np.linspace(-1.0, 1.0, num=8000, dtype=np.float32)
    original = runtime_audio._resample_poly
    runtime_audio._resample_poly = None
    try:
        output = runtime_audio.resample_audio(source, 8000, 16000)
    finally:
        runtime_audio._resample_poly = original

    assert output.dtype == np.float32
    assert len(output) == 16000
