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
        "router_canary_analytics": {
            "sample_count": 0,
            "router_decision_count": 0,
            "canary_turn_count": 0,
            "canary_coverage": 0.0,
            "fallback_count": 0,
            "shadow_compare_count": 0,
            "shadow_agreement_count": 0,
            "shadow_disagreement_count": 0,
            "shadow_agreement_rate": 0.0,
            "recent_disagreements": [],
        },
        "budget_metrics": {
            "window_sec": 3600.0,
            "sample_count": 0,
            "latency_p95_ms": {
                "stt_ms": 0.0,
                "llm_first_sentence_ms": 0.0,
                "tts_first_audio_ms": 0.0,
            },
            "tokens_per_hour": 0.0,
            "cost_usd_per_hour": 0.0,
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
        router_canary_fn = getattr(runtime, "_router_canary_analytics", None)
        if callable(router_canary_fn):
            snapshot["router_canary_analytics"] = router_canary_fn()
    set_runtime_observability_state_fn(snapshot)
