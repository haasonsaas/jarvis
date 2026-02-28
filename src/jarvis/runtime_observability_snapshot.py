"""Observability snapshot runtime helpers."""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any, Callable


def publish_observability_snapshot(
    runtime: Any,
    *,
    force: bool,
    list_summaries_fn: Callable[..., Any],
    logger: Any,
    now_monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    observability = getattr(runtime, "_observability", None)
    if observability is None:
        return
    now = now_monotonic_fn()
    if (
        not force
        and (now - runtime._last_observability_snapshot_at)
        < runtime.config.observability_snapshot_interval_sec
    ):
        return
    runtime._last_observability_snapshot_at = now
    snapshot = runtime._telemetry_snapshot()
    with suppress(Exception):
        observability.record_snapshot(snapshot)
    with suppress(Exception):
        observability.record_tool_summaries(list_summaries_fn(limit=100))
    alerts: list[dict[str, Any]] = []
    with suppress(Exception):
        alerts = observability.detect_failure_burst(window_sec=300.0)
    with suppress(Exception):
        alerts.extend(
            observability.detect_budget_violations(
                latency_p95_budget_ms=float(
                    getattr(runtime.config, "observability_latency_budget_p95_ms", 0.0)
                    or 0.0
                ),
                tokens_budget_per_hour=float(
                    getattr(runtime.config, "observability_tokens_budget_per_hour", 0.0)
                    or 0.0
                ),
                cost_budget_usd_per_hour=float(
                    getattr(runtime.config, "observability_cost_budget_usd_per_hour", 0.0)
                    or 0.0
                ),
                window_sec=float(
                    getattr(runtime.config, "observability_budget_window_sec", 3600.0)
                    or 3600.0
                ),
                cooldown_sec=float(
                    getattr(runtime.config, "observability_alert_cooldown_sec", 300.0)
                    or 300.0
                ),
            )
        )
    if alerts:
        logger.warning("Observability alerts: %s", alerts)
    runtime._publish_observability_status()
