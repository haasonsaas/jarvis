"""Quota actions for skills governance."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def skills_gov_quota_set(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _record_service_error = s._record_service_error
    _skill_quotas = s._skill_quotas
    _as_int = s._as_int
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response

    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_governance", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required for quota_set."}]}
    _skill_quotas[name] = {
        "rate_per_min": _as_int(args.get("rate_per_min", 60), 60, minimum=1, maximum=10_000),
        "cpu_sec": _as_float(args.get("cpu_sec", 15.0), 15.0, minimum=0.1, maximum=3600.0),
        "outbound_calls": _as_int(args.get("outbound_calls", 100), 100, minimum=0, maximum=100_000),
        "updated_at": time.time(),
    }
    payload = {"action": "quota_set", "name": name, "quota": dict(_skill_quotas[name]), "quota_count": len(_skill_quotas)}
    record_summary("skills_governance", "ok", start_time, effect="quota_set", risk="low")
    return _expansion_payload_response(payload)


async def skills_gov_quota_get(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _skill_quotas = s._skill_quotas
    _expansion_payload_response = s._expansion_payload_response

    name = str(args.get("name", "")).strip().lower()
    if name:
        payload = {"action": "quota_get", "name": name, "quota": dict(_skill_quotas.get(name, {}))}
    else:
        payload = {
            "action": "quota_get",
            "quota_count": len(_skill_quotas),
            "quotas": {k: dict(v) for k, v in sorted(_skill_quotas.items())},
        }
    record_summary("skills_governance", "ok", start_time, effect="quota_get", risk="low")
    return _expansion_payload_response(payload)


async def skills_gov_quota_check(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_int = s._as_int
    _as_float = s._as_float
    _skill_quotas = s._skill_quotas
    _expansion_payload_response = s._expansion_payload_response

    name = str(args.get("name", "")).strip().lower()
    usage = args.get("usage") if isinstance(args.get("usage"), dict) else {}
    quota = _skill_quotas.get(name, {})
    violations: list[str] = []
    if quota:
        if _as_int(usage.get("rate_per_min", 0), 0) > int(quota.get("rate_per_min", 0)):
            violations.append("rate_per_min")
        if _as_float(usage.get("cpu_sec", 0.0), 0.0) > float(quota.get("cpu_sec", 0.0)):
            violations.append("cpu_sec")
        if _as_int(usage.get("outbound_calls", 0), 0) > int(quota.get("outbound_calls", 0)):
            violations.append("outbound_calls")
    payload = {
        "action": "quota_check",
        "name": name,
        "quota_found": bool(quota),
        "allowed": not violations,
        "violations": violations,
        "usage": usage,
        "quota": dict(quota),
    }
    record_summary("skills_governance", "ok", start_time, effect="quota_check", risk="low")
    return _expansion_payload_response(payload)
