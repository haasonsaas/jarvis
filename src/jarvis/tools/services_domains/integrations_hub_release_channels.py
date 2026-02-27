"""Release channel handlers for integration hub."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def integration_hub_release_channel_get(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _release_channel_state = s._release_channel_state
    _json_safe_clone = s._json_safe_clone
    _release_channel_config_path = s._release_channel_config_path
    RELEASE_CHANNELS = s.RELEASE_CHANNELS

    payload = {
        "action": "release_channel_get",
        "release_channels": sorted(RELEASE_CHANNELS),
        "active_channel": str(_release_channel_state.get("active_channel", "dev")),
        "last_check_at": float(_release_channel_state.get("last_check_at", 0.0) or 0.0),
        "last_check_channel": str(_release_channel_state.get("last_check_channel", "")),
        "last_check_passed": bool(_release_channel_state.get("last_check_passed", False)),
        "migration_checks": [
            _json_safe_clone(row)
            for row in (_release_channel_state.get("migration_checks") or [])
            if isinstance(row, dict)
        ][:50],
        "release_channel_config_path": str(_release_channel_config_path),
    }
    record_summary("integration_hub", "ok", start_time, effect="release_channel_get", risk="low")
    return _expansion_payload_response(payload)


async def integration_hub_release_channel_set(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _evaluate_release_channel = s._evaluate_release_channel
    _release_channel_state = s._release_channel_state
    _json_safe_clone = s._json_safe_clone
    _release_channel_config_path = s._release_channel_config_path
    RELEASE_CHANNELS = s.RELEASE_CHANNELS

    channel = str(args.get("channel", "")).strip().lower()
    if channel not in RELEASE_CHANNELS:
        _record_service_error("integration_hub", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Unsupported channel '{channel or '<empty>'}'. Expected: dev|beta|stable.",
                }
            ]
        }
    _release_channel_state["active_channel"] = channel
    check_result = _evaluate_release_channel(channel=channel)
    _release_channel_state["last_check_at"] = time.time()
    _release_channel_state["last_check_channel"] = channel
    _release_channel_state["last_check_passed"] = bool(check_result.get("passed", False))
    _release_channel_state["migration_checks"] = [
        _json_safe_clone(row)
        for row in (check_result.get("migration_checks") or [])
        if isinstance(row, dict)
    ][:100]
    payload = {
        "action": "release_channel_set",
        "active_channel": channel,
        "check": check_result,
        "release_channel_config_path": str(_release_channel_config_path),
    }
    record_summary("integration_hub", "ok", start_time, effect=f"release_channel_set:{channel}", risk="low")
    return _expansion_payload_response(payload)


async def integration_hub_release_channel_check(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _evaluate_release_channel = s._evaluate_release_channel
    _release_channel_state = s._release_channel_state
    _json_safe_clone = s._json_safe_clone

    requested_channel = str(
        args.get("channel", _release_channel_state.get("active_channel", "dev"))
    ).strip().lower() or str(_release_channel_state.get("active_channel", "dev"))
    workspace_text = str(args.get("workspace", "")).strip()
    workspace = Path(workspace_text).expanduser() if workspace_text else Path.cwd()
    if not workspace.is_absolute():
        workspace = (Path.cwd() / workspace).resolve()
    result = _evaluate_release_channel(channel=requested_channel, workspace=workspace)
    _release_channel_state["last_check_at"] = time.time()
    _release_channel_state["last_check_channel"] = requested_channel
    _release_channel_state["last_check_passed"] = bool(result.get("passed", False))
    _release_channel_state["migration_checks"] = [
        _json_safe_clone(row)
        for row in (result.get("migration_checks") or [])
        if isinstance(row, dict)
    ][:100]
    payload = {
        "action": "release_channel_check",
        "active_channel": str(_release_channel_state.get("active_channel", "dev")),
        **result,
    }
    record_summary(
        "integration_hub",
        "ok",
        start_time,
        effect=f"release_channel_check:{requested_channel}",
        risk="low",
    )
    return _expansion_payload_response(payload)
