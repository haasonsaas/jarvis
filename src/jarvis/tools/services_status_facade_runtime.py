"""Status/scorecard helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_status_runtime import (
    duration_p95_ms as _runtime_duration_p95_ms,
    expansion_snapshot as _runtime_expansion_snapshot,
    health_rollup as _runtime_health_rollup,
    identity_status_snapshot as _runtime_identity_status_snapshot,
    integration_health_snapshot as _runtime_integration_health_snapshot,
    jarvis_scorecard_snapshot as _runtime_jarvis_scorecard_snapshot,
    observability_snapshot as _runtime_observability_snapshot,
    recent_tool_rows as _runtime_recent_tool_rows,
    score_label as _runtime_score_label,
    skills_status_snapshot as _runtime_skills_status_snapshot,
    voice_attention_snapshot as _runtime_voice_attention_snapshot,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def integration_health_snapshot() -> dict[str, Any]:
    return _runtime_integration_health_snapshot(_services_module())


def identity_status_snapshot() -> dict[str, Any]:
    return _runtime_identity_status_snapshot(_services_module())


def voice_attention_snapshot() -> dict[str, Any]:
    return _runtime_voice_attention_snapshot(_services_module())


def observability_snapshot() -> dict[str, Any]:
    return _runtime_observability_snapshot(_services_module())


def skills_status_snapshot() -> dict[str, Any]:
    return _runtime_skills_status_snapshot(_services_module())


def expansion_snapshot() -> dict[str, Any]:
    return _runtime_expansion_snapshot(_services_module())


def health_rollup(
    *,
    config_present: bool,
    memory_state: dict[str, Any] | None,
    recent_tools: list[dict[str, object]] | dict[str, str],
    identity_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _runtime_health_rollup(
        config_present=config_present,
        memory_state=memory_state,
        recent_tools=recent_tools,
        identity_status=identity_status,
    )


def score_label(score: float) -> str:
    return _runtime_score_label(_services_module(), score)


def recent_tool_rows(recent_tools: list[dict[str, object]] | dict[str, str] | Any) -> list[dict[str, object]]:
    return _runtime_recent_tool_rows(recent_tools)


def duration_p95_ms(rows: list[dict[str, object]]) -> float:
    return _runtime_duration_p95_ms(rows)


def jarvis_scorecard_snapshot(
    *,
    recent_tools: list[dict[str, object]] | dict[str, str],
    health: dict[str, Any],
    observability: dict[str, Any],
    identity: dict[str, Any],
    tool_policy: dict[str, Any],
    audit: dict[str, Any],
    integrations: dict[str, Any],
) -> dict[str, Any]:
    return _runtime_jarvis_scorecard_snapshot(
        _services_module(),
        recent_tools=recent_tools,
        health=health,
        observability=observability,
        identity=identity,
        tool_policy=tool_policy,
        audit=audit,
        integrations=integrations,
    )
