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
from jarvis.runtime_operator_status import normalize_operator_auth_mode, operator_auth_risk
from jarvis.runtime_startup import operator_control_schema, startup_blockers, startup_summary_lines
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
    assert "list_autonomy_replans" in actions
    assert "apply_autonomy_replan" in actions
    assert "copilot_actions" in actions
    assert "copilot_execute" in actions
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


def test_startup_summary_lines_include_operator_auth_and_error_taxonomy() -> None:
    runtime = SimpleNamespace(
        robot=SimpleNamespace(sim=True),
        args=SimpleNamespace(no_vision=False),
        tts=None,
        _voice_attention=SimpleNamespace(mode="wake_word", timeout_profile="normal"),
        _skills=SimpleNamespace(enabled=True),
        _observability=SimpleNamespace(),
        config=SimpleNamespace(
            motion_enabled=True,
            hand_track_enabled=False,
            home_enabled=True,
            safe_mode_enabled=False,
            home_conversation_enabled=True,
            wake_calibration_profile="default",
            memory_enabled=True,
            memory_path="/tmp/memory.sqlite",
            skills_dir="/tmp/skills",
            operator_server_enabled=True,
            operator_server_host="127.0.0.1",
            operator_server_port=8777,
            operator_auth_mode="token",
            operator_auth_token="",
            observability_db_path="/tmp/obs.sqlite",
            persona_style="composed",
            startup_warnings=["warn-a"],
            tool_allowlist=["tool-a"],
            tool_denylist=["tool-b"],
        ),
    )

    lines = startup_summary_lines(
        runtime,
        normalize_operator_auth_mode_fn=normalize_operator_auth_mode,
        operator_auth_risk_fn=operator_auth_risk,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        tool_service_error_codes={"timeout", "unknown_error"},
        telemetry_service_error_details={"timeout"},
        telemetry_storage_error_details={"storage_error"},
    )

    joined = "\n".join(lines)
    assert "Mode: simulation" in joined
    assert "Operator server: on" in joined
    assert "mode=token" in joined
    assert "token=missing" in joined
    assert "Tool policy: allow=1 deny=1" in joined
    assert "Error taxonomy: total=2 service=1 storage=1" in joined
