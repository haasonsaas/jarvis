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
        assert config.safe_mode_enabled is False

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

    def test_wake_mode_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(wake_mode="invalid-mode")
        assert c.wake_mode == "always_listening"

    def test_wake_calibration_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(wake_calibration_profile="street-noise")
        assert c.wake_calibration_profile == "default"

    def test_voice_timeout_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(voice_timeout_profile="dynamic")
        assert c.voice_timeout_profile == "normal"

    def test_home_permission_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(home_permission_profile="execute-all")
        assert c.home_permission_profile == "control"

    def test_home_conversation_permission_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(home_conversation_permission_profile="execute-all")
        assert c.home_conversation_permission_profile == "readonly"

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

    def test_nudge_policy_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config

        c = Config(nudge_policy="force")
        assert c.nudge_policy == "adaptive"

    def test_email_permission_profile_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(email_permission_profile="send-all")
        assert c.email_permission_profile == "readonly"

    def test_weather_units_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config
        c = Config(weather_units="kelvin")
        assert c.weather_units == "metric"

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
        monkeypatch.setenv("WEATHER_TIMEOUT_SEC", "0")
        monkeypatch.setenv("WEBHOOK_TIMEOUT_SEC", "-3")
        monkeypatch.setenv("TURN_TIMEOUT_ACT_SEC", "0")
        monkeypatch.setenv("BACKCHANNEL_STYLE", "LOUD")
        monkeypatch.setenv("PERSONA_STYLE", "chatty")
        monkeypatch.setenv("HOME_ENABLED", "maybe")
        monkeypatch.setenv("SAFE_MODE_ENABLED", "sometimes")
        monkeypatch.setenv("HOME_REQUIRE_CONFIRM_EXECUTE", "sometimes")
        monkeypatch.setenv("HOME_CONVERSATION_ENABLED", "perhaps")
        monkeypatch.setenv("PLAN_PREVIEW_REQUIRE_ACK", "later")
        monkeypatch.setenv("MEMORY_PII_GUARDRAILS_ENABLED", "unknown")
        monkeypatch.setenv("HOME_PERMISSION_PROFILE", "execute-all")
        monkeypatch.setenv("HOME_CONVERSATION_PERMISSION_PROFILE", "execute-all")
        monkeypatch.setenv("TODOIST_PERMISSION_PROFILE", "write-all")
        monkeypatch.setenv("NOTIFICATION_PERMISSION_PROFILE", "enabled")
        monkeypatch.setenv("NUDGE_POLICY", "force")
        monkeypatch.setenv("NUDGE_QUIET_HOURS_START", "25:00")
        monkeypatch.setenv("NUDGE_QUIET_HOURS_END", "bad")
        monkeypatch.setenv("EMAIL_PERMISSION_PROFILE", "send-all")
        monkeypatch.setenv("EMAIL_TIMEOUT_SEC", "0")
        monkeypatch.setenv("WEATHER_UNITS", "kelvin")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "DOA_TIMEOUT invalid" in text
        assert "DOA_CHANGE_THRESHOLD invalid" in text
        assert "MEMORY_SEARCH_LIMIT invalid" in text
        assert "TODOIST_TIMEOUT_SEC invalid" in text
        assert "PUSHOVER_TIMEOUT_SEC invalid" in text
        assert "WEATHER_TIMEOUT_SEC invalid" in text
        assert "WEBHOOK_TIMEOUT_SEC invalid" in text
        assert "TURN_TIMEOUT_ACT_SEC invalid" in text
        assert "BACKCHANNEL_STYLE invalid" in text
        assert "PERSONA_STYLE invalid" in text
        assert "HOME_ENABLED invalid boolean" in text
        assert "SAFE_MODE_ENABLED invalid boolean" in text
        assert "HOME_REQUIRE_CONFIRM_EXECUTE invalid boolean" in text
        assert "HOME_CONVERSATION_ENABLED invalid boolean" in text
        assert "PLAN_PREVIEW_REQUIRE_ACK invalid boolean" in text
        assert "MEMORY_PII_GUARDRAILS_ENABLED invalid boolean" in text
        assert "HOME_PERMISSION_PROFILE invalid" in text
        assert "HOME_CONVERSATION_PERMISSION_PROFILE invalid" in text
        assert "TODOIST_PERMISSION_PROFILE invalid" in text
        assert "NOTIFICATION_PERMISSION_PROFILE invalid" in text
        assert "NUDGE_POLICY invalid" in text
        assert "NUDGE_QUIET_HOURS_START invalid" in text
        assert "NUDGE_QUIET_HOURS_END invalid" in text
        assert "EMAIL_PERMISSION_PROFILE invalid" in text
        assert "EMAIL_TIMEOUT_SEC invalid" in text
        assert "WEATHER_UNITS invalid" in text

    def test_invalid_bool_env_falls_back_to_default_behavior(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_ENABLED", "invalid")
        monkeypatch.setenv("MEMORY_ENABLED", "invalid")
        monkeypatch.setenv("HOME_CONVERSATION_ENABLED", "invalid")
        monkeypatch.setenv("MEMORY_PII_GUARDRAILS_ENABLED", "invalid")
        from jarvis.config import Config

        c = Config()
        assert c.home_enabled is True
        assert c.memory_enabled is True
        assert c.home_require_confirm_execute is False
        assert c.home_conversation_enabled is False
        assert c.memory_pii_guardrails_enabled is True

    def test_home_require_confirm_execute_env_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_REQUIRE_CONFIRM_EXECUTE", "true")
        from jarvis.config import Config

        c = Config()
        assert c.home_require_confirm_execute is True

    def test_safe_mode_enabled_env_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("SAFE_MODE_ENABLED", "true")
        from jarvis.config import Config

        c = Config()
        assert c.safe_mode_enabled is True
        assert any("SAFE_MODE_ENABLED=true" in warning for warning in c.startup_warnings)

    def test_home_conversation_enabled_env_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_CONVERSATION_ENABLED", "true")
        from jarvis.config import Config

        c = Config()
        assert c.home_conversation_enabled is True

    def test_plan_preview_require_ack_env_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("PLAN_PREVIEW_REQUIRE_ACK", "true")
        from jarvis.config import Config

        c = Config()
        assert c.plan_preview_require_ack is True

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
        monkeypatch.setenv("EMAIL_TIMEOUT_SEC", "0")
        monkeypatch.setenv("WEATHER_TIMEOUT_SEC", "0")
        monkeypatch.setenv("WEBHOOK_TIMEOUT_SEC", "-1")
        monkeypatch.setenv("TURN_TIMEOUT_ACT_SEC", "0")
        from jarvis.config import Config

        c = Config()
        assert c.todoist_timeout_sec == 10.0
        assert c.pushover_timeout_sec == 10.0
        assert c.email_timeout_sec == 10.0
        assert c.weather_timeout_sec == 8.0
        assert c.webhook_timeout_sec == 8.0
        assert c.turn_timeout_act_sec == 30.0

    def test_timeout_env_values_can_be_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("TODOIST_TIMEOUT_SEC", "7.5")
        monkeypatch.setenv("PUSHOVER_TIMEOUT_SEC", "12")
        monkeypatch.setenv("EMAIL_TIMEOUT_SEC", "11")
        monkeypatch.setenv("WEATHER_TIMEOUT_SEC", "4.5")
        monkeypatch.setenv("WEBHOOK_TIMEOUT_SEC", "9")
        monkeypatch.setenv("TURN_TIMEOUT_ACT_SEC", "6.5")
        from jarvis.config import Config

        c = Config()
        assert c.todoist_timeout_sec == 7.5
        assert c.pushover_timeout_sec == 12.0
        assert c.email_timeout_sec == 11.0
        assert c.weather_timeout_sec == 4.5
        assert c.webhook_timeout_sec == 9.0
        assert c.turn_timeout_act_sec == 6.5

    def test_retention_env_values_fall_back_to_defaults_when_invalid(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("MEMORY_RETENTION_DAYS", "-1")
        monkeypatch.setenv("AUDIT_RETENTION_DAYS", "-5")
        from jarvis.config import Config

        c = Config()
        assert c.memory_retention_days == 0.0
        assert c.audit_retention_days == 0.0
        text = "\n".join(c.startup_warnings)
        assert "MEMORY_RETENTION_DAYS invalid" in text
        assert "AUDIT_RETENTION_DAYS invalid" in text

    def test_startup_warnings_flag_short_tokens_and_insecure_webhooks(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "short")
        monkeypatch.setenv("TODOIST_API_TOKEN", "tiny")
        monkeypatch.setenv("PUSHOVER_API_TOKEN", "small")
        monkeypatch.setenv("PUSHOVER_USER_KEY", "user")
        monkeypatch.setenv("WEBHOOK_AUTH_TOKEN", "token")
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://slack.test/hook")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://discord.test/hook")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "HASS_TOKEN appears unusually short" in text
        assert "TODOIST_API_TOKEN appears unusually short" in text
        assert "PUSHOVER_API_TOKEN appears unusually short" in text
        assert "WEBHOOK_AUTH_TOKEN is set while WEBHOOK_ALLOWLIST is empty" in text
        assert "SLACK_WEBHOOK_URL should use https." in text
        assert "DISCORD_WEBHOOK_URL should use https." in text

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

    def test_startup_warning_for_partial_email_config(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
        monkeypatch.delenv("EMAIL_FROM", raising=False)
        monkeypatch.delenv("EMAIL_DEFAULT_TO", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "email config incomplete" in text.lower()

    def test_startup_warning_for_partial_quiet_window_config(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("NUDGE_QUIET_HOURS_START", "22:00")
        monkeypatch.setenv("NUDGE_QUIET_HOURS_END", "")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "quiet-window config incomplete" in text.lower()

    def test_startup_warning_for_permissive_profiles_without_credentials(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("HOME_PERMISSION_PROFILE", "control")
        monkeypatch.setenv("HOME_CONVERSATION_PERMISSION_PROFILE", "control")
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
        assert "home_conversation_permission_profile=control set while hass_url/hass_token are empty" in text
        assert "todoist_permission_profile=control set while todoist_api_token is empty" in text
        assert "notification_permission_profile=allow set while pushover credentials are empty" in text

    def test_identity_profile_parsing_and_normalization(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("IDENTITY_ENFORCEMENT_ENABLED", "true")
        monkeypatch.setenv("IDENTITY_DEFAULT_USER", "  OWNER  ")
        monkeypatch.setenv("IDENTITY_DEFAULT_PROFILE", "trusted")
        monkeypatch.setenv("IDENTITY_USER_PROFILES", "alice=readonly,bob=DENY,charlie=unknown")
        monkeypatch.setenv("IDENTITY_TRUSTED_USERS", "owner,alice,owner")
        monkeypatch.setenv("IDENTITY_REQUIRE_APPROVAL", "true")
        monkeypatch.setenv("IDENTITY_APPROVAL_CODE", "strong-secret")
        from jarvis.config import Config

        c = Config()
        assert c.identity_enforcement_enabled is True
        assert c.identity_default_user == "owner"
        assert c.identity_default_profile == "trusted"
        assert c.identity_user_profiles["alice"] == "readonly"
        assert c.identity_user_profiles["bob"] == "deny"
        assert c.identity_user_profiles["charlie"] == "control"
        assert c.identity_trusted_users == ["alice", "owner"]
        assert c.identity_require_approval is True
        assert c.identity_approval_code == "strong-secret"

    def test_identity_startup_warnings_for_invalid_profiles_and_missing_approval_path(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("IDENTITY_ENFORCEMENT_ENABLED", "true")
        monkeypatch.setenv("IDENTITY_REQUIRE_APPROVAL", "true")
        monkeypatch.setenv("IDENTITY_USER_PROFILES", "badentry,=readonly,user=super")
        monkeypatch.setenv("IDENTITY_DEFAULT_PROFILE", "super")
        monkeypatch.setenv("IDENTITY_APPROVAL_CODE", "short")
        monkeypatch.delenv("IDENTITY_TRUSTED_USERS", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "IDENTITY_DEFAULT_PROFILE invalid" in text
        assert "IDENTITY_USER_PROFILES has invalid entry" in text
        assert "IDENTITY_USER_PROFILES has invalid profile" in text
        assert "IDENTITY_APPROVAL_CODE appears unusually short" in text

    def test_identity_require_approval_warning_when_no_code_or_trusted_users(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("IDENTITY_ENFORCEMENT_ENABLED", "true")
        monkeypatch.setenv("IDENTITY_REQUIRE_APPROVAL", "true")
        monkeypatch.delenv("IDENTITY_APPROVAL_CODE", raising=False)
        monkeypatch.delenv("IDENTITY_TRUSTED_USERS", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "IDENTITY_REQUIRE_APPROVAL is enabled without IDENTITY_APPROVAL_CODE or IDENTITY_TRUSTED_USERS." in text

    def test_plan_preview_warning_when_identity_enforcement_disabled(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("PLAN_PREVIEW_REQUIRE_ACK", "true")
        monkeypatch.setenv("IDENTITY_ENFORCEMENT_ENABLED", "false")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "PLAN_PREVIEW_REQUIRE_ACK enabled while IDENTITY_ENFORCEMENT_ENABLED=false" in text

    def test_model_secondary_mode_normalizes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        from jarvis.config import Config

        c = Config(model_secondary_mode="unknown")
        assert c.model_secondary_mode == "offline_stub"

    def test_startup_warning_for_signature_requirement_without_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("SKILLS_REQUIRE_SIGNATURE", "true")
        monkeypatch.delenv("SKILLS_SIGNATURE_KEY", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "SKILLS_REQUIRE_SIGNATURE enabled without SKILLS_SIGNATURE_KEY" in text

    def test_startup_warning_for_encryption_without_data_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("MEMORY_ENCRYPTION_ENABLED", "true")
        monkeypatch.delenv("JARVIS_DATA_KEY", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "Encryption enabled without JARVIS_DATA_KEY" in text

    def test_startup_warning_for_inbound_webhook_without_auth(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("WEBHOOK_INBOUND_ENABLED", "true")
        monkeypatch.delenv("WEBHOOK_INBOUND_TOKEN", raising=False)
        monkeypatch.delenv("WEBHOOK_AUTH_TOKEN", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "WEBHOOK_INBOUND_ENABLED=true without WEBHOOK_INBOUND_TOKEN/WEBHOOK_AUTH_TOKEN" in text

    def test_startup_warning_for_non_loopback_operator_host(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("OPERATOR_SERVER_ENABLED", "true")
        monkeypatch.setenv("OPERATOR_SERVER_HOST", "0.0.0.0")
        monkeypatch.delenv("OPERATOR_AUTH_TOKEN", raising=False)
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "OPERATOR_SERVER_HOST is non-loopback" in text
        assert "OPERATOR_AUTH_TOKEN should be set when OPERATOR_SERVER_HOST is non-loopback." in text

    def test_startup_warning_for_short_operator_auth_token(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("OPERATOR_AUTH_TOKEN", "short")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "OPERATOR_AUTH_TOKEN appears unusually short" in text

    def test_startup_warning_when_inbound_enabled_but_operator_disabled(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("OPERATOR_SERVER_ENABLED", "false")
        monkeypatch.setenv("WEBHOOK_INBOUND_ENABLED", "true")
        from jarvis.config import Config

        c = Config()
        text = "\n".join(c.startup_warnings)
        assert "WEBHOOK_INBOUND_ENABLED=true while OPERATOR_SERVER_ENABLED=false" in text
