"""Runtime observability status helpers."""

from __future__ import annotations

from typing import Any


def default_observability_status_snapshot() -> dict[str, Any]:
    return {
        "enabled": False,
        "uptime_sec": 0.0,
        "restart_count": 0,
        "alerts": [],
        "intent_metrics": {
            "turn_count": 0.0,
            "answer_intent_count": 0.0,
            "action_intent_count": 0.0,
            "hybrid_intent_count": 0.0,
            "answer_sample_count": 0.0,
            "completion_sample_count": 0.0,
            "answer_quality_success_rate": 0.0,
            "completion_success_rate": 0.0,
            "correction_count": 0.0,
            "correction_frequency": 0.0,
            "preference_update_turns": 0.0,
            "preference_update_fields": 0.0,
        },
        "multimodal_metrics": {
            "turn_count": 0.0,
            "avg_confidence": 0.0,
            "low_confidence_count": 0.0,
            "low_confidence_rate": 0.0,
        },
        "latency_dashboards": {
            "sample_count": 0,
            "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "by_intent": {},
            "by_tool_mix": {},
            "by_wake_mode": {},
        },
        "policy_decision_analytics": {
            "decision_count": 0,
            "by_tool": {},
            "by_status": {},
            "by_reason": {},
            "by_user": {},
            "by_user_tool": {},
        },
    }


def publish_observability_status(
    runtime: Any,
    *,
    set_runtime_observability_state_fn: Any,
    default_snapshot_fn: Any = default_observability_status_snapshot,
) -> None:
    observability = getattr(runtime, "_observability", None)
    if observability is None:
        set_runtime_observability_state_fn(default_snapshot_fn())
        return
    try:
        snapshot = observability.status_snapshot()
    except Exception:
        snapshot = default_snapshot_fn()
    if isinstance(snapshot, dict):
        snapshot["latency_dashboards"] = runtime._conversation_latency_analytics()
        snapshot["policy_decision_analytics"] = runtime._policy_decision_analytics()
    set_runtime_observability_state_fn(snapshot)
