"""Shared fixtures for Jarvis tests.

All hardware dependencies (robot, audio, camera, APIs) are mocked.
Tests should run without any external services or devices.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock

# Set required env vars before any imports touch Config
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("ELEVENLABS_API_KEY", "test-key-not-real")


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Config with test defaults."""
    monkeypatch.setenv("MEMORY_PATH", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("EXPANSION_STATE_PATH", str(tmp_path / "expansion-state.json"))
    monkeypatch.setenv("NOTES_CAPTURE_DIR", str(tmp_path / "notes"))
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path / "quality-reports"))
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("RELEASE_CHANNEL_CONFIG_PATH", str(project_root / "config" / "release-channels.json"))
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


def _aiohttp_context_manager(response: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.fixture
def aiohttp_response():
    """Factory for aiohttp-like response mocks."""

    def _build(
        *,
        status: int = 200,
        json_data=None,
        json_side_effect=None,
        text_data: str = "",
        text_side_effect=None,
    ) -> AsyncMock:
        response = AsyncMock()
        response.status = status
        if json_side_effect is not None:
            response.json = AsyncMock(side_effect=json_side_effect)
        else:
            response.json = AsyncMock(return_value=json_data)
        if text_side_effect is not None:
            response.text = AsyncMock(side_effect=text_side_effect)
        else:
            response.text = AsyncMock(return_value=text_data)
        return response

    return _build


@pytest.fixture
def aiohttp_session_mock():
    """Factory for aiohttp.ClientSession context manager mocks."""

    def _build(*, get=None, post=None) -> AsyncMock:
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        if get is None:
            session.get = MagicMock()
        elif isinstance(get, list):
            session.get = MagicMock(side_effect=[_aiohttp_context_manager(resp) for resp in get])
        else:
            session.get = MagicMock(return_value=_aiohttp_context_manager(get))

        if post is None:
            session.post = MagicMock()
        elif isinstance(post, list):
            session.post = MagicMock(side_effect=[_aiohttp_context_manager(resp) for resp in post])
        else:
            session.post = MagicMock(return_value=_aiohttp_context_manager(post))

        return session

    return _build
