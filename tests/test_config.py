"""Tests for jarvis.config."""

import os
import pytest


class TestConfig:
    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test-456")
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "ha-token")

        from jarvis.config import Config
        c = Config()
        assert c.anthropic_api_key == "sk-test-123"
        assert c.elevenlabs_api_key == "el-test-456"
        assert c.hass_url == "http://ha.local:8123"
        assert c.has_home_assistant is True

    def test_missing_anthropic_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from jarvis.config import Config
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            Config()

    def test_defaults(self, config):
        assert config.sample_rate == 16000
        assert config.vad_threshold == 0.5
        assert config.whisper_model == "base.en"
        assert config.yolo_model == "yolov8n-face.pt"
        assert config.motion_enabled is True
        assert config.home_enabled is True

    def test_invalid_sample_rate_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        with pytest.raises(ValueError, match="16000"):
            Config(sample_rate=44100)

    def test_has_home_assistant_false_when_missing(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.delenv("HASS_URL", raising=False)
        monkeypatch.delenv("HASS_TOKEN", raising=False)

        from jarvis.config import Config
        c = Config()
        assert c.has_home_assistant is False
