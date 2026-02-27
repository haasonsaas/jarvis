from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.runtime_observability_status import (
    default_observability_status_snapshot,
    publish_observability_status,
)


def test_default_observability_status_snapshot_shape() -> None:
    snapshot = default_observability_status_snapshot()
    assert snapshot["enabled"] is False
    assert "intent_metrics" in snapshot
    assert "latency_dashboards" in snapshot
    assert "policy_decision_analytics" in snapshot


def test_publish_observability_status_uses_default_when_disabled() -> None:
    runtime = SimpleNamespace(_observability=None)
    payload: dict[str, object] = {}

    publish_observability_status(
        runtime,
        set_runtime_observability_state_fn=lambda value: payload.update(value),
    )

    assert payload["enabled"] is False
    assert payload["latency_dashboards"]["sample_count"] == 0


def test_publish_observability_status_enriches_snapshot_with_analytics() -> None:
    runtime = SimpleNamespace(
        _observability=SimpleNamespace(status_snapshot=lambda: {"enabled": True, "alerts": []}),
        _conversation_latency_analytics=lambda: {"sample_count": 3},
        _policy_decision_analytics=lambda: {"decision_count": 2},
    )
    payload: dict[str, object] = {}

    publish_observability_status(
        runtime,
        set_runtime_observability_state_fn=lambda value: payload.update(value),
    )

    assert payload["enabled"] is True
    assert payload["latency_dashboards"]["sample_count"] == 3
    assert payload["policy_decision_analytics"]["decision_count"] == 2


def test_publish_observability_status_falls_back_when_snapshot_raises() -> None:
    runtime = SimpleNamespace(
        _observability=SimpleNamespace(status_snapshot=MagicMock(side_effect=RuntimeError("boom"))),
        _conversation_latency_analytics=lambda: {"sample_count": 1},
        _policy_decision_analytics=lambda: {"decision_count": 1},
    )
    payload: dict[str, object] = {}

    publish_observability_status(
        runtime,
        set_runtime_observability_state_fn=lambda value: payload.update(value),
    )

    assert payload["enabled"] is False
    assert payload["latency_dashboards"]["sample_count"] == 1
    assert payload["policy_decision_analytics"]["decision_count"] == 1
