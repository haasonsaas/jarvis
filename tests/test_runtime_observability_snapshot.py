from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.runtime_observability_snapshot import publish_observability_snapshot


def test_publish_observability_snapshot_respects_interval_guard() -> None:
    observability = SimpleNamespace(
        record_snapshot=MagicMock(),
        record_tool_summaries=MagicMock(),
        detect_failure_burst=MagicMock(return_value=[]),
    )
    runtime = SimpleNamespace(
        _observability=observability,
        _last_observability_snapshot_at=100.0,
        config=SimpleNamespace(observability_snapshot_interval_sec=5.0),
        _telemetry_snapshot=lambda: {"turns": 1.0},
        _publish_observability_status=MagicMock(),
    )

    publish_observability_snapshot(
        runtime,
        force=False,
        list_summaries_fn=lambda limit=100: [],
        logger=SimpleNamespace(warning=MagicMock()),
        now_monotonic_fn=lambda: 102.0,
    )

    observability.record_snapshot.assert_not_called()
    runtime._publish_observability_status.assert_not_called()


def test_publish_observability_snapshot_records_snapshot_summaries_and_alerts() -> None:
    observability = SimpleNamespace(
        record_snapshot=MagicMock(),
        record_tool_summaries=MagicMock(),
        detect_failure_burst=MagicMock(return_value=["burst-a"]),
    )
    logger = SimpleNamespace(warning=MagicMock())
    runtime = SimpleNamespace(
        _observability=observability,
        _last_observability_snapshot_at=0.0,
        config=SimpleNamespace(observability_snapshot_interval_sec=5.0),
        _telemetry_snapshot=lambda: {"turns": 2.0},
        _publish_observability_status=MagicMock(),
    )

    publish_observability_snapshot(
        runtime,
        force=False,
        list_summaries_fn=lambda limit=100: [{"name": "tool_summary", "status": "ok"}],
        logger=logger,
        now_monotonic_fn=lambda: 20.0,
    )

    observability.record_snapshot.assert_called_once_with({"turns": 2.0})
    observability.record_tool_summaries.assert_called_once()
    logger.warning.assert_called_once()
    runtime._publish_observability_status.assert_called_once()


def test_publish_observability_snapshot_noop_when_observability_missing() -> None:
    runtime = SimpleNamespace(
        _observability=None,
        _last_observability_snapshot_at=0.0,
        config=SimpleNamespace(observability_snapshot_interval_sec=5.0),
        _telemetry_snapshot=lambda: {"turns": 0.0},
        _publish_observability_status=MagicMock(),
    )

    publish_observability_snapshot(
        runtime,
        force=True,
        list_summaries_fn=lambda limit=100: [],
        logger=SimpleNamespace(warning=MagicMock()),
        now_monotonic_fn=lambda: 1.0,
    )

    runtime._publish_observability_status.assert_not_called()
