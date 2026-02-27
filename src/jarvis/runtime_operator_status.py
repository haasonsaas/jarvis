"""Operator status payload helpers for the Jarvis runtime."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable


def _severity_rank(level: str) -> int:
    if level == "high":
        return 3
    if level == "medium":
        return 2
    return 1


def _recommendations(
    *,
    operator: dict[str, Any],
    runtime_invariants: dict[str, Any],
    status: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    max_severity = "low"

    def add(level: str, code: str, message: str) -> None:
        nonlocal max_severity
        rows.append({"severity": level, "code": code, "message": message})
        if _severity_rank(level) > _severity_rank(max_severity):
            max_severity = level

    auth_risk = str(operator.get("auth_risk", "medium")).strip().lower()
    if auth_risk == "high":
        add(
            "high",
            "operator_auth_risk",
            "Operator auth risk is high; configure session auth with a token.",
        )
    elif auth_risk == "medium":
        add(
            "medium",
            "operator_auth_harden",
            "Use session auth mode to reduce operator endpoint risk.",
        )

    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    health_level = str(health.get("health_level", "ok")).strip().lower()
    if health_level == "error":
        add("high", "runtime_health_error", "Runtime health is error; inspect status reasons.")
    elif health_level == "degraded":
        add("medium", "runtime_health_degraded", "Runtime health is degraded; inspect status reasons.")

    reasons = health.get("reasons") if isinstance(health.get("reasons"), list) else []
    if reasons:
        add("medium", "health_reasons_present", f"Health reasons present: {len(reasons)}.")

    invariant_total = int(runtime_invariants.get("total_violations", 0) or 0)
    if invariant_total > 0:
        add(
            "medium",
            "runtime_invariants",
            f"Runtime invariants recorded {invariant_total} violation(s); review recent auto-heals.",
        )

    plan_preview = status.get("plan_preview") if isinstance(status.get("plan_preview"), dict) else {}
    pending_preview_count = int(plan_preview.get("pending_count", 0) or 0)
    if pending_preview_count > 0:
        add(
            "medium",
            "pending_previews",
            f"{pending_preview_count} plan preview(s) awaiting acknowledgment.",
        )

    expansion = status.get("expansion") if isinstance(status.get("expansion"), dict) else {}
    planner = expansion.get("planner_engine") if isinstance(expansion.get("planner_engine"), dict) else {}
    waiting_checkpoint_count = int(planner.get("autonomy_waiting_checkpoint_count", 0) or 0)
    if waiting_checkpoint_count > 0:
        add(
            "medium",
            "autonomy_waiting_checkpoint",
            f"{waiting_checkpoint_count} autonomy task(s) are waiting for checkpoint approval.",
        )

    voice_attention = (
        status.get("voice_attention")
        if isinstance(status.get("voice_attention"), dict)
        else {}
    )
    multimodal = (
        voice_attention.get("multimodal_grounding")
        if isinstance(voice_attention.get("multimodal_grounding"), dict)
        else {}
    )
    confidence_band = str(multimodal.get("confidence_band", "")).strip().lower()
    if confidence_band == "low":
        add(
            "medium",
            "multimodal_low_confidence",
            "Multimodal grounding is low; use confirmations for high-impact actions.",
        )

    if not rows:
        add("low", "healthy", "No immediate operator action required.")

    return {
        "severity": max_severity,
        "count": len(rows),
        "recommended": rows,
    }


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
    status["operator_recommendations"] = _recommendations(
        operator=status["operator"],
        runtime_invariants=status["runtime_invariants"],
        status=status,
    )
    return status
