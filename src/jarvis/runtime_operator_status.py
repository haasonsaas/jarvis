"""Operator status payload helpers for the Jarvis runtime."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable


async def operator_status_provider(
    runtime: Any,
    *,
    valid_operator_auth_modes: set[str],
    valid_control_presets: set[str],
    system_status_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        payload = await system_status_fn({})
        text = payload.get("content", [{}])[0].get("text", "{}")
        status = json.loads(text) if isinstance(text, str) else {}
        if not isinstance(status, dict):
            status = {}
    except Exception as exc:
        status = {"error": str(exc)}

    latest = runtime._operator_conversation_trace_provider(limit=1)
    latest_turn_id = (
        int(latest[0].get("turn_id", 0))
        if latest and isinstance(latest[0], dict)
        else 0
    )

    auth_mode = str(getattr(runtime.config, "operator_auth_mode", "token")).strip().lower()
    if auth_mode not in valid_operator_auth_modes:
        auth_mode = "token"

    status["operator"] = {
        "enabled": bool(runtime.config.operator_server_enabled),
        "host": runtime.config.operator_server_host,
        "port": int(runtime.config.operator_server_port),
        "auth_mode": auth_mode,
        "auth_required": auth_mode != "off",
        "auth_token_configured": bool(
            str(getattr(runtime.config, "operator_auth_token", "")).strip()
        ),
    }

    token_set = bool(status["operator"]["auth_token_configured"])
    if auth_mode == "off":
        status["operator"]["auth_risk"] = "high"
    elif not token_set:
        status["operator"]["auth_risk"] = "high"
    elif auth_mode == "session":
        status["operator"]["auth_risk"] = "low"
    else:
        status["operator"]["auth_risk"] = "medium"

    status["conversation_trace"] = {
        "recent_count": len(runtime._conversation_traces),
        "latest_turn_id": latest_turn_id,
    }

    episodes = runtime._operator_episodic_timeline_provider(limit=20)
    latest_episode_id = (
        int(episodes[0].get("episode_id", 0))
        if episodes and isinstance(episodes[0], dict)
        else 0
    )
    status["episodic_timeline"] = {
        "recent_count": len(getattr(runtime, "_episodic_timeline", [])),
        "latest_episode_id": latest_episode_id,
        "recent": episodes,
    }

    preview = getattr(runtime, "_personality_preview_snapshot", None)
    status["personality_preview"] = {
        "active": isinstance(preview, dict),
        "baseline": dict(preview) if isinstance(preview, dict) else None,
        "current": {
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
        },
    }

    status["operator_controls"] = {
        "active_control_preset": str(getattr(runtime, "_active_control_preset", "custom")),
        "available_control_presets": sorted(valid_control_presets),
        "runtime_profile": runtime._runtime_profile_snapshot(),
    }
    status["runtime_invariants"] = runtime._runtime_invariant_snapshot()
    return status
