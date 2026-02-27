"""Scorecard runtime helpers for services domains."""

from __future__ import annotations

import math
import time
from typing import Any


def score_label(services_module: Any, score: float) -> str:
    value = services_module._as_float(score, 0.0, minimum=0.0, maximum=1.0)
    if value >= 0.9:
        return "excellent"
    if value >= 0.75:
        return "strong"
    if value >= 0.6:
        return "fair"
    return "weak"


def recent_tool_rows(recent_tools: list[dict[str, object]] | dict[str, str] | Any) -> list[dict[str, object]]:
    if not isinstance(recent_tools, list):
        return []
    rows: list[dict[str, object]] = []
    for row in recent_tools:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def duration_p95_ms(rows: list[dict[str, object]]) -> float:
    durations: list[float] = []
    for row in rows:
        try:
            value = float(row.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        if math.isfinite(value) and value >= 0.0:
            durations.append(value)
    if not durations:
        return 0.0
    ordered = sorted(durations)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[index]


def jarvis_scorecard_snapshot(
    services_module: Any,
    *,
    recent_tools: list[dict[str, object]] | dict[str, str],
    health: dict[str, Any],
    observability: dict[str, Any],
    identity: dict[str, Any],
    tool_policy: dict[str, Any],
    audit: dict[str, Any],
    integrations: dict[str, Any],
) -> dict[str, Any]:
    s = services_module
    rows = recent_tool_rows(recent_tools)

    p95_ms = duration_p95_ms(rows)
    latency_score = 0.75 if p95_ms <= 0.0 else max(0.0, min(1.0, 1.0 - (p95_ms / 4000.0)))

    success_statuses = {"ok", "dry_run", "noop", "cooldown", "empty"}
    failure_statuses = {"error", "denied"}
    success_count = 0
    failure_count = 0
    for row in rows:
        status = str(row.get("status", "")).strip().lower()
        if status in success_statuses:
            success_count += 1
        elif status in failure_statuses:
            failure_count += 1
    total_scored = success_count + failure_count
    success_rate = (success_count / total_scored) if total_scored > 0 else 0.85
    reliability_score = success_rate
    health_level = str(health.get("health_level", "ok")).strip().lower()
    if health_level == "degraded":
        reliability_score -= 0.08
    elif health_level == "error":
        reliability_score -= 0.20
    open_breakers = 0
    if isinstance(integrations, dict):
        for payload in integrations.values():
            if not isinstance(payload, dict):
                continue
            breaker = payload.get("circuit_breaker")
            if isinstance(breaker, dict) and bool(breaker.get("open")):
                open_breakers += 1
    reliability_score -= min(0.25, open_breakers * 0.05)
    reliability_score = s._as_float(reliability_score, 0.0, minimum=0.0, maximum=1.0)

    intent = observability.get("intent_metrics") if isinstance(observability, dict) else None
    intent_payload = intent if isinstance(intent, dict) else {}
    turn_count = s._as_float(intent_payload.get("turn_count", 0.0), 0.0, minimum=0.0)
    action_count = s._as_float(intent_payload.get("action_intent_count", 0.0), 0.0, minimum=0.0)
    hybrid_count = s._as_float(intent_payload.get("hybrid_intent_count", 0.0), 0.0, minimum=0.0)
    completion_success = s._as_float(intent_payload.get("completion_success_rate", 0.0), 0.0, minimum=0.0, maximum=1.0)
    correction_frequency = s._as_float(intent_payload.get("correction_frequency", 0.0), 0.0, minimum=0.0, maximum=1.0)
    if turn_count <= 0.0:
        action_or_hybrid_ratio = 0.0
        initiative_score = 0.50
    else:
        action_or_hybrid_ratio = max(0.0, min(1.0, (action_count + hybrid_count) / turn_count))
        action_signal = min(1.0, action_or_hybrid_ratio / 0.35)
        correction_signal = max(0.0, 1.0 - min(1.0, correction_frequency / 0.25))
        initiative_score = (0.45 * completion_success) + (0.35 * action_signal) + (0.20 * correction_signal)
    initiative_score = s._as_float(initiative_score, 0.0, minimum=0.0, maximum=1.0)

    identity_enabled = bool(identity.get("enabled")) if isinstance(identity, dict) else False
    require_approval = bool(identity.get("require_approval")) if isinstance(identity, dict) else False
    trusted_users = s._as_int(identity.get("trusted_user_count", 0), 0, minimum=0) if isinstance(identity, dict) else 0
    approval_code_configured = bool(identity.get("approval_code_configured")) if isinstance(identity, dict) else False
    approval_configured = approval_code_configured or trusted_users > 0
    safe_mode_enabled = bool(tool_policy.get("safe_mode_enabled")) if isinstance(tool_policy, dict) else False
    plan_preview_ack = bool(tool_policy.get("plan_preview_require_ack")) if isinstance(tool_policy, dict) else False
    audit_redaction = bool(audit.get("redaction_enabled")) if isinstance(audit, dict) else False
    audit_encrypted = bool(audit.get("encrypted")) if isinstance(audit, dict) else False
    trust_score = 0.30
    trust_score += 0.20 if identity_enabled else 0.08
    trust_score += 0.14 if require_approval and approval_configured else (0.04 if require_approval else 0.10)
    trust_score += 0.10 if plan_preview_ack else 0.04
    trust_score += 0.12 if audit_redaction else 0.0
    trust_score += 0.06 if audit_encrypted else 0.0
    trust_score += 0.06 if safe_mode_enabled else 0.0
    if require_approval and not approval_configured:
        trust_score -= 0.15
    trust_score = s._as_float(trust_score, 0.0, minimum=0.0, maximum=1.0)

    weights = {
        "latency": 0.30,
        "reliability": 0.30,
        "initiative": 0.20,
        "trust": 0.20,
    }
    overall_score = (
        (weights["latency"] * latency_score)
        + (weights["reliability"] * reliability_score)
        + (weights["initiative"] * initiative_score)
        + (weights["trust"] * trust_score)
    )
    overall_score = s._as_float(overall_score, 0.0, minimum=0.0, maximum=1.0)

    return {
        "overall": {
            "score": round(overall_score, 4),
            "grade": score_label(s, overall_score),
        },
        "dimensions": {
            "latency": {
                "score": round(latency_score, 4),
                "grade": score_label(s, latency_score),
                "p95_ms": round(p95_ms, 2),
                "sample_count": len(rows),
            },
            "reliability": {
                "score": round(reliability_score, 4),
                "grade": score_label(s, reliability_score),
                "success_rate": round(s._as_float(success_rate, 0.0, minimum=0.0, maximum=1.0), 4),
                "failure_rate": round(1.0 - s._as_float(success_rate, 0.0, minimum=0.0, maximum=1.0), 4),
                "open_circuit_breakers": open_breakers,
            },
            "initiative": {
                "score": round(initiative_score, 4),
                "grade": score_label(s, initiative_score),
                "completion_success_rate": round(completion_success, 4),
                "action_or_hybrid_ratio": round(action_or_hybrid_ratio, 4),
                "correction_frequency": round(correction_frequency, 4),
            },
            "trust": {
                "score": round(trust_score, 4),
                "grade": score_label(s, trust_score),
                "identity_enabled": identity_enabled,
                "approval_required": require_approval,
                "approval_configured": approval_configured,
                "safe_mode_enabled": safe_mode_enabled,
                "plan_preview_ack_required": plan_preview_ack,
                "audit_redaction_enabled": audit_redaction,
                "audit_encrypted": audit_encrypted,
            },
        },
        "weights": weights,
        "computed_at": time.time(),
    }
