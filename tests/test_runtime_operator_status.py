from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.runtime_constants import (
    VALID_CONTROL_PRESETS,
    VALID_OPERATOR_AUTH_MODES,
)
from jarvis.runtime_operator_status import (
    normalize_operator_auth_mode,
    operator_auth_risk,
    operator_status_provider,
)


def _collect_paths(value: object, *, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            paths.add(path)
            paths.update(_collect_paths(nested, prefix=path))
        return paths
    if isinstance(value, list):
        list_path = f"{prefix}[]" if prefix else "[]"
        paths.add(list_path)
        if value:
            paths.update(_collect_paths(value[0], prefix=list_path))
        return paths
    return paths


def test_normalize_operator_auth_mode_defaults_to_token_for_invalid() -> None:
    assert normalize_operator_auth_mode("bad-mode", valid_modes=VALID_OPERATOR_AUTH_MODES) == "token"
    assert normalize_operator_auth_mode("SESSION", valid_modes=VALID_OPERATOR_AUTH_MODES) == "session"


@pytest.mark.parametrize(
    ("mode", "token_configured", "expected"),
    [
        ("off", False, "high"),
        ("off", True, "high"),
        ("token", False, "high"),
        ("token", True, "medium"),
        ("session", False, "high"),
        ("session", True, "low"),
    ],
)
def test_operator_auth_risk_matrix(mode: str, token_configured: bool, expected: str) -> None:
    assert operator_auth_risk(auth_mode=mode, token_configured=token_configured) == expected


@pytest.mark.asyncio
async def test_operator_status_provider_shapes_payload_and_risk() -> None:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(
        operator_server_enabled=True,
        operator_server_host="127.0.0.1",
        operator_server_port=8080,
        operator_auth_mode="session",
        operator_auth_token="tok",
        persona_style="friendly",
        backchannel_style="expressive",
    )
    runtime._conversation_traces = deque([{"turn_id": 11}], maxlen=10)
    runtime._episodic_timeline = deque([{"episode_id": 7}], maxlen=10)
    runtime._active_control_preset = "quiet_hours"
    runtime._personality_preview_snapshot = {"persona_style": "composed"}
    runtime._runtime_profile_snapshot = lambda: {"wake_mode": "wake_word"}
    runtime._runtime_invariant_snapshot = lambda: {"total_violations": 0}
    runtime._operator_conversation_trace_provider = lambda limit=1: [{"turn_id": 11}]
    runtime._operator_episodic_timeline_provider = lambda limit=20: [{"episode_id": 7}]

    async def _system_status(_: dict[str, object]) -> dict[str, object]:
        return {"content": [{"text": '{"ok": true, "service": "jarvis"}'}]}

    status = await operator_status_provider(
        runtime,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        valid_control_presets=VALID_CONTROL_PRESETS,
        system_status_fn=_system_status,
    )

    assert status["ok"] is True
    assert status["operator"]["auth_mode"] == "session"
    assert status["operator"]["auth_risk"] == "low"
    assert status["conversation_trace"]["latest_turn_id"] == 11
    assert status["episodic_timeline"]["latest_episode_id"] == 7
    assert status["operator_controls"]["active_control_preset"] == "quiet_hours"
    assert status["operator_controls"]["runtime_profile"]["wake_mode"] == "wake_word"
    recommendations = status["operator_recommendations"]
    assert recommendations["severity"] == "low"
    assert recommendations["count"] >= 1
    assert recommendations["recommended"][0]["code"] == "healthy"


@pytest.mark.asyncio
async def test_operator_status_provider_normalizes_invalid_auth_mode() -> None:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(
        operator_server_enabled=True,
        operator_server_host="0.0.0.0",
        operator_server_port=8080,
        operator_auth_mode="bad-mode",
        operator_auth_token="",
        persona_style="friendly",
        backchannel_style="balanced",
    )
    runtime._conversation_traces = deque([], maxlen=10)
    runtime._episodic_timeline = deque([], maxlen=10)
    runtime._active_control_preset = "custom"
    runtime._personality_preview_snapshot = None
    runtime._runtime_profile_snapshot = lambda: {}
    runtime._runtime_invariant_snapshot = lambda: {}
    runtime._operator_conversation_trace_provider = lambda limit=1: []
    runtime._operator_episodic_timeline_provider = lambda limit=20: []

    async def _system_status(_: dict[str, object]) -> dict[str, object]:
        return {"content": [{"text": "{}"}]}

    status = await operator_status_provider(
        runtime,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        valid_control_presets=VALID_CONTROL_PRESETS,
        system_status_fn=_system_status,
    )

    assert status["operator"]["auth_mode"] == "token"
    assert status["operator"]["auth_risk"] == "high"
    recommendations = status["operator_recommendations"]
    assert recommendations["severity"] in {"medium", "high"}
    assert any(
        row["code"] == "operator_auth_risk"
        for row in recommendations["recommended"]
    )


@pytest.mark.asyncio
async def test_operator_status_provider_recommends_on_health_and_checkpoint_signals() -> None:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(
        operator_server_enabled=True,
        operator_server_host="127.0.0.1",
        operator_server_port=8080,
        operator_auth_mode="token",
        operator_auth_token="set-token",
        persona_style="friendly",
        backchannel_style="balanced",
    )
    runtime._conversation_traces = deque([], maxlen=10)
    runtime._episodic_timeline = deque([], maxlen=10)
    runtime._active_control_preset = "custom"
    runtime._personality_preview_snapshot = None
    runtime._runtime_profile_snapshot = lambda: {}
    runtime._runtime_invariant_snapshot = lambda: {"total_violations": 3}
    runtime._operator_conversation_trace_provider = lambda limit=1: []
    runtime._operator_episodic_timeline_provider = lambda limit=20: []

    async def _system_status(_: dict[str, object]) -> dict[str, object]:
        payload = {
            "health": {"health_level": "degraded", "reasons": ["memory_error"]},
            "plan_preview": {"pending_count": 2},
            "expansion": {"planner_engine": {"autonomy_waiting_checkpoint_count": 1}},
            "voice_attention": {
                "multimodal_grounding": {
                    "confidence_band": "low",
                    "overall_confidence": 0.2,
                }
            },
        }
        return {"content": [{"text": str(payload).replace("'", '"')}]}

    status = await operator_status_provider(
        runtime,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        valid_control_presets=VALID_CONTROL_PRESETS,
        system_status_fn=_system_status,
    )

    recommendations = status["operator_recommendations"]
    assert recommendations["severity"] in {"medium", "high"}
    codes = {row["code"] for row in recommendations["recommended"]}
    assert "runtime_health_degraded" in codes
    assert "pending_previews" in codes
    assert "autonomy_waiting_checkpoint" in codes
    assert "multimodal_low_confidence" in codes


@pytest.mark.asyncio
async def test_operator_status_snapshot_contract_paths_stable() -> None:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(
        operator_server_enabled=True,
        operator_server_host="127.0.0.1",
        operator_server_port=8080,
        operator_auth_mode="session",
        operator_auth_token="tok",
        persona_style="friendly",
        backchannel_style="balanced",
    )
    runtime._conversation_traces = deque([{"turn_id": 11}], maxlen=10)
    runtime._episodic_timeline = deque([{"episode_id": 7}], maxlen=10)
    runtime._active_control_preset = "custom"
    runtime._personality_preview_snapshot = {"persona_style": "composed"}
    runtime._runtime_profile_snapshot = lambda: {"wake_mode": "wake_word"}
    runtime._runtime_invariant_snapshot = lambda: {"total_violations": 0}
    runtime._operator_conversation_trace_provider = lambda limit=1: [{"turn_id": 11}]
    runtime._operator_episodic_timeline_provider = lambda limit=20: [{"episode_id": 7}]

    async def _system_status(_: dict[str, object]) -> dict[str, object]:
        return {"content": [{"text": '{"ok": true, "service": "jarvis"}'}]}

    status = await operator_status_provider(
        runtime,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        valid_control_presets=VALID_CONTROL_PRESETS,
        system_status_fn=_system_status,
    )

    snapshot_path = Path(__file__).resolve().parents[1] / "docs" / "evals" / "operator-status-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    required_paths = _collect_paths(snapshot)
    actual_paths = _collect_paths(status)
    missing = sorted(required_paths - actual_paths)
    assert not missing


@pytest.mark.asyncio
async def test_operator_status_recommendation_codes_stress_contract() -> None:
    runtime = SimpleNamespace()
    runtime.config = SimpleNamespace(
        operator_server_enabled=True,
        operator_server_host="127.0.0.1",
        operator_server_port=8080,
        operator_auth_mode="token",
        operator_auth_token="",
        persona_style="friendly",
        backchannel_style="balanced",
    )
    runtime._conversation_traces = deque([], maxlen=10)
    runtime._episodic_timeline = deque([], maxlen=10)
    runtime._active_control_preset = "custom"
    runtime._personality_preview_snapshot = None
    runtime._runtime_profile_snapshot = lambda: {}
    runtime._runtime_invariant_snapshot = lambda: {"total_violations": 3}
    runtime._operator_conversation_trace_provider = lambda limit=1: []
    runtime._operator_episodic_timeline_provider = lambda limit=20: []

    async def _system_status(_: dict[str, object]) -> dict[str, object]:
        payload = {
            "health": {"health_level": "degraded", "reasons": ["memory_error"]},
            "plan_preview": {"pending_count": 2},
            "expansion": {"planner_engine": {"autonomy_waiting_checkpoint_count": 1}},
            "voice_attention": {"multimodal_grounding": {"confidence_band": "low"}},
        }
        return {"content": [{"text": json.dumps(payload)}]}

    status = await operator_status_provider(
        runtime,
        valid_operator_auth_modes=VALID_OPERATOR_AUTH_MODES,
        valid_control_presets=VALID_CONTROL_PRESETS,
        system_status_fn=_system_status,
    )

    codes = {row["code"] for row in status["operator_recommendations"]["recommended"]}
    required_codes = {
        "operator_auth_risk",
        "runtime_health_degraded",
        "health_reasons_present",
        "runtime_invariants",
        "pending_previews",
        "autonomy_waiting_checkpoint",
        "multimodal_low_confidence",
    }
    assert required_codes.issubset(codes)
