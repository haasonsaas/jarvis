"""Circuit-breaker helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_circuit_runtime import (
    ensure_circuit_breaker_state as _runtime_ensure_circuit_breaker_state,
    integration_circuit_open as _runtime_integration_circuit_open,
    integration_circuit_open_message as _runtime_integration_circuit_open_message,
    integration_circuit_snapshot as _runtime_integration_circuit_snapshot,
    integration_for_tool as _runtime_integration_for_tool,
    integration_record_failure as _runtime_integration_record_failure,
    integration_record_success as _runtime_integration_record_success,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def integration_for_tool(tool_name: str) -> str | None:
    return _runtime_integration_for_tool(_services_module(), tool_name)


def ensure_circuit_breaker_state(integration: str) -> dict[str, Any]:
    return _runtime_ensure_circuit_breaker_state(_services_module(), integration)


def integration_circuit_open(integration: str, *, now_ts: float | None = None) -> tuple[bool, float]:
    return _runtime_integration_circuit_open(_services_module(), integration, now_ts=now_ts)


def integration_record_failure(integration: str, error_code: str) -> None:
    _runtime_integration_record_failure(_services_module(), integration, error_code)


def integration_record_success(integration: str) -> None:
    _runtime_integration_record_success(_services_module(), integration)


def integration_circuit_snapshot(integration: str, *, now_ts: float | None = None) -> dict[str, Any]:
    return _runtime_integration_circuit_snapshot(_services_module(), integration, now_ts=now_ts)


def integration_circuit_open_message(integration: str, remaining_sec: float) -> str:
    return _runtime_integration_circuit_open_message(integration, remaining_sec)
