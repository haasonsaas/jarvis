from __future__ import annotations

from types import SimpleNamespace

from jarvis.runtime_constants import (
    VALID_BACKCHANNEL_STYLES,
    VALID_CONTROL_PRESETS,
    VALID_OPERATOR_AUTH_MODES,
    VALID_PERSONA_STYLES,
    VALID_VOICE_PROFILE_CONFIRMATIONS,
    VALID_VOICE_PROFILE_PACE,
    VALID_VOICE_PROFILE_TONE,
    VALID_VOICE_PROFILE_VERBOSITY,
)
from jarvis.runtime_startup import operator_control_schema, startup_blockers
from jarvis.voice_attention import VALID_TIMEOUT_PROFILES, VALID_WAKE_MODES


def test_operator_control_schema_exposes_expected_actions_and_enums() -> None:
    schema = operator_control_schema(
        valid_wake_modes=VALID_WAKE_MODES,
        valid_timeout_profiles=VALID_TIMEOUT_PROFILES,
        valid_persona_styles=VALID_PERSONA_STYLES,
        valid_backchannel_styles=VALID_BACKCHANNEL_STYLES,
        valid_voice_profile_verbosity=VALID_VOICE_PROFILE_VERBOSITY,
        valid_voice_profile_confirmations=VALID_VOICE_PROFILE_CONFIRMATIONS,
        valid_voice_profile_pace=VALID_VOICE_PROFILE_PACE,
        valid_voice_profile_tone=VALID_VOICE_PROFILE_TONE,
        valid_control_presets=VALID_CONTROL_PRESETS,
    )

    actions = schema["actions"]
    assert "set_wake_mode" in actions
    assert "set_voice_profile" in actions
    assert "apply_control_preset" in actions
    assert actions["set_wake_mode"]["enum"]["mode"] == sorted(VALID_WAKE_MODES)
    assert actions["apply_control_preset"]["enum"]["preset"] == sorted(
        VALID_CONTROL_PRESETS
    )


def test_startup_blockers_disabled_when_not_strict() -> None:
    config = SimpleNamespace(startup_strict=False)
    args = SimpleNamespace(no_tts=False)

    blockers = startup_blockers(
        config=config,
        args=args,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
    )

    assert blockers == []


def test_startup_blockers_include_security_and_token_requirements() -> None:
    config = SimpleNamespace(
        startup_strict=True,
        elevenlabs_api_key="",
        operator_server_enabled=True,
        operator_server_host="",
        operator_auth_mode="token",
        operator_auth_token="",
        skills_require_signature=True,
        skills_signature_key="",
        memory_encryption_enabled=True,
        audit_encryption_enabled=False,
        data_encryption_key="",
        webhook_inbound_enabled=True,
        webhook_inbound_token="",
        webhook_auth_token="",
    )
    args = SimpleNamespace(no_tts=False)

    blockers = startup_blockers(
        config=config,
        args=args,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
    )

    assert any("ELEVENLABS_API_KEY" in item for item in blockers)
    assert any("OPERATOR_SERVER_HOST" in item for item in blockers)
    assert any("OPERATOR_AUTH_MODE=token" in item for item in blockers)
    assert any("SKILLS_SIGNATURE_KEY" in item for item in blockers)
    assert any("JARVIS_DATA_KEY" in item for item in blockers)
    assert any("WEBHOOK_INBOUND_ENABLED" in item for item in blockers)
