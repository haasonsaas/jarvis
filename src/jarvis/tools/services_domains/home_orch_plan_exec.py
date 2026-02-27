"""Plan, execute, and area-policy handlers for home orchestrator."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_orch_plan(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _home_plan_from_request = s._home_plan_from_request

    request_text = str(args.get("request_text", "")).strip()
    plan = _home_plan_from_request(request_text)
    payload = {
        "action": "plan",
        "request_text": request_text,
        "plan_label": plan["label"],
        "step_count": len(plan["steps"]),
        "steps": plan["steps"],
    }
    record_summary("home_orchestrator", "ok", start_time, effect=f"plan:{plan['label']}", risk="low")
    return _expansion_payload_response(payload)


async def home_orch_execute(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _home_area_policy_violation = s._home_area_policy_violation

    actions = args.get("actions") if isinstance(args.get("actions"), list) else []
    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in actions:
        if not isinstance(row, dict):
            results.append({"status": "failed", "reason": "invalid_action_entry"})
            continue
        domain = str(row.get("domain", "")).strip().lower()
        tool_action = str(row.get("action", "")).strip().lower()
        entity_id = str(row.get("entity_id", "")).strip().lower()
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if not domain or not tool_action or not entity_id:
            results.append({"status": "failed", "reason": "missing_fields", "entry": row})
            continue
        pair = f"{domain}:{tool_action}:{entity_id}"
        if pair in seen_keys:
            results.append({"status": "failed", "reason": "duplicate_action", "entry": row})
            continue
        seen_keys.add(pair)
        blocked, reason = _home_area_policy_violation(
            domain=domain,
            action=tool_action,
            entity_id=entity_id,
            data=data,
        )
        if blocked:
            results.append({"status": "failed", "reason": "area_policy", "detail": reason, "entry": row})
            continue
        results.append({"status": "ok", "entry": row, "preflight": "passed"})
    ok_count = sum(1 for item in results if item.get("status") == "ok")
    fail_count = len(results) - ok_count
    payload = {
        "action": "execute",
        "executed_count": ok_count,
        "failed_count": fail_count,
        "partial_failure": ok_count > 0 and fail_count > 0,
        "results": results,
    }
    record_summary("home_orchestrator", "ok", start_time, effect=f"execute_ok={ok_count}_fail={fail_count}", risk="medium" if fail_count else "low")
    return _expansion_payload_response(payload)


async def home_orch_area_policy_set(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _home_area_policies = s._home_area_policies
    _as_str_list = s._as_str_list

    area = str(args.get("area", "")).strip().lower()
    policy = args.get("policy") if isinstance(args.get("policy"), dict) else {}
    if not area:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "area is required for area_policy_set."}]}
    _home_area_policies[area] = {
        "blocked_actions": sorted(set(_as_str_list(policy.get("blocked_actions"), lower=True))),
        "quiet_hours_start": str(policy.get("quiet_hours_start", "")).strip(),
        "quiet_hours_end": str(policy.get("quiet_hours_end", "")).strip(),
        "updated_at": time.time(),
    }
    payload = {"action": "area_policy_set", "area": area, "policy": dict(_home_area_policies[area]), "policy_count": len(_home_area_policies)}
    record_summary("home_orchestrator", "ok", start_time, effect="area_policy_set", risk="low")
    return _expansion_payload_response(payload)


async def home_orch_area_policy_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _home_area_policies = s._home_area_policies

    area = str(args.get("area", "")).strip().lower()
    if area:
        payload = {"action": "area_policy_list", "area": area, "policy": dict(_home_area_policies.get(area, {}))}
    else:
        payload = {"action": "area_policy_list", "policy_count": len(_home_area_policies), "policies": {name: dict(row) for name, row in sorted(_home_area_policies.items())}}
    record_summary("home_orchestrator", "ok", start_time, effect="area_policy_list", risk="low")
    return _expansion_payload_response(payload)
