"""Integration circuit-breaker runtime helpers for services domains."""

from __future__ import annotations

import time
from typing import Any


def integration_for_tool(services_module: Any, tool_name: str) -> str | None:
    return services_module.INTEGRATION_TOOL_MAP.get(str(tool_name).strip().lower())


def ensure_circuit_breaker_state(services_module: Any, integration: str) -> dict[str, Any]:
    s = services_module
    normalized = str(integration or "").strip().lower()
    if not normalized:
        normalized = "unknown"
    state = s._integration_circuit_breakers.get(normalized)
    if state is not None:
        return state
    state = {
        "integration": normalized,
        "consecutive_failures": 0,
        "open_until": 0.0,
        "opened_count": 0,
        "cooldown_sec": 0.0,
        "last_error": "",
        "last_failure_at": 0.0,
        "last_success_at": 0.0,
    }
    s._integration_circuit_breakers[normalized] = state
    return state


def integration_circuit_open(
    services_module: Any,
    integration: str,
    *,
    now_ts: float | None = None,
) -> tuple[bool, float]:
    state = ensure_circuit_breaker_state(services_module, integration)
    now = time.time() if now_ts is None else float(now_ts)
    open_until = float(state.get("open_until", 0.0) or 0.0)
    if open_until <= now:
        return False, 0.0
    return True, max(0.0, open_until - now)


def integration_record_failure(services_module: Any, integration: str, error_code: str) -> None:
    s = services_module
    normalized_code = str(error_code or "").strip().lower()
    if normalized_code not in s.CIRCUIT_BREAKER_ERROR_CODES:
        return
    state = ensure_circuit_breaker_state(s, integration)
    now = time.time()
    failures = int(state.get("consecutive_failures", 0)) + 1
    state["consecutive_failures"] = failures
    state["last_error"] = normalized_code
    state["last_failure_at"] = now
    if failures < s.CIRCUIT_BREAKER_FAILURE_THRESHOLD:
        return
    opened_count = int(state.get("opened_count", 0))
    cooldown = min(
        s.CIRCUIT_BREAKER_MAX_COOLDOWN_SEC,
        s.CIRCUIT_BREAKER_BASE_COOLDOWN_SEC * (2 ** max(0, opened_count)),
    )
    state["cooldown_sec"] = float(cooldown)
    state["open_until"] = now + float(cooldown)
    state["opened_count"] = opened_count + 1


def integration_record_success(services_module: Any, integration: str) -> None:
    state = ensure_circuit_breaker_state(services_module, integration)
    state["consecutive_failures"] = 0
    state["open_until"] = 0.0
    state["cooldown_sec"] = 0.0
    state["last_error"] = ""
    state["last_success_at"] = time.time()


def integration_circuit_snapshot(
    services_module: Any,
    integration: str,
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    state = ensure_circuit_breaker_state(services_module, integration)
    now = time.time() if now_ts is None else float(now_ts)
    open_until = float(state.get("open_until", 0.0) or 0.0)
    return {
        "open": open_until > now,
        "open_remaining_sec": max(0.0, open_until - now),
        "consecutive_failures": int(state.get("consecutive_failures", 0)),
        "opened_count": int(state.get("opened_count", 0)),
        "cooldown_sec": float(state.get("cooldown_sec", 0.0) or 0.0),
        "last_error": str(state.get("last_error", "")),
        "last_failure_at": float(state.get("last_failure_at", 0.0) or 0.0),
        "last_success_at": float(state.get("last_success_at", 0.0) or 0.0),
    }


def integration_circuit_open_message(integration: str, remaining_sec: float) -> str:
    label = str(integration).replace("_", " ").strip() or "integration"
    return f"{label.title()} circuit breaker is open; retry in about {int(max(1.0, remaining_sec))}s."
