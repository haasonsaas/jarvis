"""Tests for jarvis.config."""

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

    def test_whitespace_only_anthropic_key_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")

        from jarvis.config import Config
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            Config()

    def test_required_env_value_is_trimmed(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "  sk-trimmed  ")

        from jarvis.config import Config
        c = Config()
        assert c.anthropic_api_key == "sk-trimmed"

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

    def test_invalid_vad_threshold_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        with pytest.raises(ValueError, match="vad_threshold"):
            Config(vad_threshold=1.5)

    def test_invalid_face_track_fps_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        with pytest.raises(ValueError, match="face_track_fps"):
            Config(face_track_fps=0)

    def test_invalid_memory_weights_raise(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        with pytest.raises(ValueError, match="memory_hybrid_weight"):
            Config(memory_hybrid_weight=-0.1)

    def test_backchannel_style_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(backchannel_style="LOUD")
        assert c.backchannel_style == "balanced"

    def test_persona_style_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(persona_style="chatty")
        assert c.persona_style == "composed"

    def test_home_permission_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(home_permission_profile="execute-all")
        assert c.home_permission_profile == "control"

    def test_todoist_permission_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(todoist_permission_profile="write-all")
        assert c.todoist_permission_profile == "control"

    def test_notification_permission_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(notification_permission_profile="enabled")
        assert c.notification_permission_profile == "allow"

    def test_invalid_audit_retention_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        with pytest.raises(ValueError, match="audit_log_max_bytes"):
            Config(audit_log_max_bytes=0)
        with pytest.raises(ValueError, match="audit_log_backups"):
            Config(audit_log_backups=0)

    def test_startup_warnings_include_invalid_optional_env_values(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("DOA_TIMEOUT", "nan")
        monkeypatch.setenv("DOA_CHANGE_THRESHOLD", "inf")
        monkeypatch.setenv("MEMORY_SEARCH_LIMIT", "oops")
        monkeypatch.setenv("TODOIST_TIMEOUT_SEC", "0")
        monkeypatch.setenv("PUSHOVER_TIMEOUT_SEC", "-5")
        monkeypatch.setenv("BACKCHANNEL_STYLE", "LOUD")
        monkeypatch.setenv("PERSONA_STYLE", "chatty")
        monkeypatch.setenv("HOME_ENABLED", "maybe")
        monkeypatch.setenv("HOME_REQUIRE_CONFIRM_EXECUTE", "sometimes")
        monkeypatch.setenv("HOME_CONVERSATION_ENABLED", "perhaps")
        monkeypatch.setenv("HOME_PERMISSION_PROFILE", "execute-all")
        monkeypatch.setenv("TODOIST_PERMISSION_PROFILE", "write-all")
        monkeypatch.setenv("NOTIFICATION_PERMISSION_PROFILE", "enabled")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "DOA_TIMEOUT invalid" in text
        assert "DOA_CHANGE_THRESHOLD invalid" in text
        assert "MEMORY_SEARCH_LIMIT invalid" in text
        assert "TODOIST_TIMEOUT_SEC invalid" in text
        assert "PUSHOVER_TIMEOUT_SEC invalid" in text
        assert "BACKCHANNEL_STYLE invalid" in text
        assert "PERSONA_STYLE invalid" in text
        assert "HOME_ENABLED invalid boolean" in text
        assert "HOME_REQUIRE_CONFIRM_EXECUTE invalid boolean" in text
        assert "HOME_CONVERSATION_ENABLED invalid boolean" in text
        assert "HOME_PERMISSION_PROFILE invalid" in text
        assert "TODOIST_PERMISSION_PROFILE invalid" in text
        assert "NOTIFICATION_PERMISSION_PROFILE invalid" in text

    def test_invalid_bool_env_falls_back_to_default_behavior(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_ENABLED", "invalid")
        monkeypatch.setenv("MEMORY_ENABLED", "invalid")
        monkeypatch.setenv("HOME_CONVERSATION_ENABLED", "invalid")
        from jarvis.config import Config

        c = Config()
        assert c.home_enabled is True
        assert c.memory_enabled is True
        assert c.home_require_confirm_execute is False
        assert c.home_conversation_enabled is False

    def test_home_require_confirm_execute_env_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_REQUIRE_CONFIRM_EXECUTE", "true")
        from jarvis.config import Config

        c = Config()
        assert c.home_require_confirm_execute is True

    def test_home_conversation_enabled_env_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_CONVERSATION_ENABLED", "true")
        from jarvis.config import Config

        c = Config()
        assert c.home_conversation_enabled is True

    def test_non_finite_float_env_values_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("DOA_TIMEOUT", "nan")
        monkeypatch.setenv("DOA_CHANGE_THRESHOLD", "inf")
        from jarvis.config import Config

        c = Config()
        assert c.doa_timeout == 1.0
        assert c.doa_change_threshold == 0.04

    def test_timeout_env_values_fall_back_to_defaults_when_invalid(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("TODOIST_TIMEOUT_SEC", "0")
        monkeypatch.setenv("PUSHOVER_TIMEOUT_SEC", "-5")
        from jarvis.config import Config

        c = Config()
        assert c.todoist_timeout_sec == 10.0
        assert c.pushover_timeout_sec == 10.0

    def test_timeout_env_values_can_be_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("TODOIST_TIMEOUT_SEC", "7.5")
        monkeypatch.setenv("PUSHOVER_TIMEOUT_SEC", "12")
        from jarvis.config import Config

        c = Config()
        assert c.todoist_timeout_sec == 7.5
        assert c.pushover_timeout_sec == 12.0

    def test_startup_warning_for_partial_home_assistant_config(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "home assistant config incomplete" in text.lower()

    def test_startup_warning_for_partial_todoist_config(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("TODOIST_PROJECT_ID", "inbox")
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "todoist config incomplete" in text.lower()

    def test_startup_warning_for_partial_pushover_config(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("PUSHOVER_API_TOKEN", "app-token")
        monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "pushover config incomplete" in text.lower()

    def test_startup_warning_for_permissive_profiles_without_credentials(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_PERMISSION_PROFILE", "control")
        monkeypatch.setenv("TODOIST_PERMISSION_PROFILE", "control")
        monkeypatch.setenv("NOTIFICATION_PERMISSION_PROFILE", "allow")
        monkeypatch.delenv("HASS_URL", raising=False)
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        monkeypatch.delenv("PUSHOVER_API_TOKEN", raising=False)
        monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings).lower()
        assert "home_permission_profile=control set while hass_url/hass_token are empty" in text
        assert "todoist_permission_profile=control set while todoist_api_token is empty" in text
        assert "notification_permission_profile=allow set while pushover credentials are empty" in text
