"""Shared fixtures for Jarvis tests.

All hardware dependencies (robot, audio, camera, APIs) are mocked.
Tests should run without any external services or devices.
"""

from __future__ import annotations

import os
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch

# Set required env vars before any imports touch Config
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("ELEVENLABS_API_KEY", "test-key-not-real")


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Config with test defaults."""
    monkeypatch.setenv("MEMORY_PATH", str(tmp_path / "memory.sqlite"))
    from jarvis.config import Config
    return Config()


@pytest.fixture
def mock_robot():
    """A RobotController in simulation mode."""
    from jarvis.robot.controller import RobotController
    robot = RobotController(sim=True)
    robot.connect()
    return robot


@pytest.fixture
def presence(mock_robot):
    """A PresenceLoop bound to a simulated robot (not started)."""
    from jarvis.presence import PresenceLoop
    return PresenceLoop(mock_robot)


@pytest.fixture
def audio_16k_silence():
    """512 samples of silence at 16kHz (one VAD chunk)."""
    return np.zeros(512, dtype=np.float32)


@pytest.fixture
def audio_16k_noise():
    """512 samples of white noise at 16kHz (one VAD chunk)."""
    rng = np.random.default_rng(42)
    return rng.standard_normal(512).astype(np.float32) * 0.5


@pytest.fixture
def sample_frame():
    """A dummy 480x640 RGB camera frame."""
    return np.zeros((480, 640, 3), dtype=np.uint8)
