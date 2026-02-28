"""Data-driven policy engine helpers for services runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_policy_engine() -> dict[str, Any]:
    return {
        "version": "1",
        "execution": {
            "high_risk_domains": ["lock", "alarm_control_panel"],
            "require_confirm_domains": ["lock", "alarm_control_panel", "cover"],
            "effect_verification_domains": [
                "light",
                "switch",
                "fan",
                "climate",
                "cover",
                "lock",
                "media_player",
            ],
            "max_actions_per_execute": 25,
        },
        "identity": {
            "step_up_token_ttl_sec": 900.0,
            "step_up_required_domains": [],
            "min_trust_score_for_high_risk": 0.6,
        },
        "autonomy_slo": {
            "max_replan_rate": 0.25,
            "max_verification_failure_rate": 0.2,
            "max_backlog_steps": 25,
            "max_minutes_since_last_cycle": 30.0,
        },
        "router": {
            "shadow_mode": False,
            "canary_percent": 0.0,
        },
    }


def _as_number(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for row in value[:200]:
        text = str(row).strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def normalize_policy_engine(raw: Any) -> dict[str, Any]:
    base = default_policy_engine()
    payload = raw if isinstance(raw, dict) else {}

    execution_raw = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    identity_raw = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    slo_raw = payload.get("autonomy_slo") if isinstance(payload.get("autonomy_slo"), dict) else {}
    router_raw = payload.get("router") if isinstance(payload.get("router"), dict) else {}

    normalized = {
        "version": str(payload.get("version", base["version"])) or base["version"],
        "execution": {
            "high_risk_domains": _as_str_list(
                execution_raw.get("high_risk_domains", base["execution"]["high_risk_domains"])
            )
            or list(base["execution"]["high_risk_domains"]),
            "require_confirm_domains": _as_str_list(
                execution_raw.get("require_confirm_domains", base["execution"]["require_confirm_domains"])
            )
            or list(base["execution"]["require_confirm_domains"]),
            "effect_verification_domains": _as_str_list(
                execution_raw.get(
                    "effect_verification_domains",
                    base["execution"]["effect_verification_domains"],
                )
            )
            or list(base["execution"]["effect_verification_domains"]),
            "max_actions_per_execute": _as_int(
                execution_raw.get("max_actions_per_execute", base["execution"]["max_actions_per_execute"]),
                int(base["execution"]["max_actions_per_execute"]),
                minimum=1,
                maximum=500,
            ),
        },
        "identity": {
            "step_up_token_ttl_sec": _as_number(
                identity_raw.get("step_up_token_ttl_sec", base["identity"]["step_up_token_ttl_sec"]),
                float(base["identity"]["step_up_token_ttl_sec"]),
                minimum=30.0,
                maximum=86_400.0,
            ),
            "step_up_required_domains": _as_str_list(
                identity_raw.get("step_up_required_domains", base["identity"]["step_up_required_domains"])
            )
            or list(base["identity"]["step_up_required_domains"]),
            "min_trust_score_for_high_risk": _as_number(
                identity_raw.get(
                    "min_trust_score_for_high_risk",
                    base["identity"]["min_trust_score_for_high_risk"],
                ),
                float(base["identity"]["min_trust_score_for_high_risk"]),
                minimum=0.0,
                maximum=1.0,
            ),
        },
        "autonomy_slo": {
            "max_replan_rate": _as_number(
                slo_raw.get("max_replan_rate", base["autonomy_slo"]["max_replan_rate"]),
                float(base["autonomy_slo"]["max_replan_rate"]),
                minimum=0.0,
                maximum=1.0,
            ),
            "max_verification_failure_rate": _as_number(
                slo_raw.get(
                    "max_verification_failure_rate",
                    base["autonomy_slo"]["max_verification_failure_rate"],
                ),
                float(base["autonomy_slo"]["max_verification_failure_rate"]),
                minimum=0.0,
                maximum=1.0,
            ),
            "max_backlog_steps": _as_int(
                slo_raw.get("max_backlog_steps", base["autonomy_slo"]["max_backlog_steps"]),
                int(base["autonomy_slo"]["max_backlog_steps"]),
                minimum=0,
                maximum=100_000,
            ),
            "max_minutes_since_last_cycle": _as_number(
                slo_raw.get(
                    "max_minutes_since_last_cycle",
                    base["autonomy_slo"]["max_minutes_since_last_cycle"],
                ),
                float(base["autonomy_slo"]["max_minutes_since_last_cycle"]),
                minimum=1.0,
                maximum=1440.0,
            ),
        },
        "router": {
            "shadow_mode": bool(router_raw.get("shadow_mode", base["router"]["shadow_mode"])),
            "canary_percent": _as_number(
                router_raw.get("canary_percent", base["router"]["canary_percent"]),
                float(base["router"]["canary_percent"]),
                minimum=0.0,
                maximum=100.0,
            ),
        },
    }
    return normalized


def load_policy_engine(path: Path) -> tuple[dict[str, Any], str]:
    source = "default"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return normalize_policy_engine(payload), "file"
        except Exception:
            source = "default_invalid_file"
    return normalize_policy_engine({}), source


def domain_in_policy(domains: list[str], domain: str) -> bool:
    normalized = str(domain or "").strip().lower()
    if not normalized:
        return False
    return normalized in {str(item).strip().lower() for item in domains if str(item).strip()}
