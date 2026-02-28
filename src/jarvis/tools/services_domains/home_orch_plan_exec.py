"""Plan, execute, and area-policy handlers for home orchestrator."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

APPROVAL_QUEUE_MAX = 500
APPROVAL_TTL_SEC = 30.0 * 60.0


def _services():
    from jarvis.tools import services as s

    return s


def _normalize_action_row(row: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(row, dict):
        return None, "invalid_action_entry"
    domain = str(row.get("domain", "")).strip().lower()
    tool_action = str(row.get("action", "")).strip().lower()
    entity_id = str(row.get("entity_id", "")).strip().lower()
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    if not domain or not tool_action or not entity_id:
        return None, "missing_fields"
    return {
        "domain": domain,
        "action": tool_action,
        "entity_id": entity_id,
        "data": dict(data),
    }, None


def _approval_queue(proactive_state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = proactive_state.get("approval_requests")
    if isinstance(rows, list):
        return rows
    rows = []
    proactive_state["approval_requests"] = rows
    return rows


def _action_fingerprint(actions: list[dict[str, Any]]) -> str:
    canonical = json.dumps(actions, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _execution_ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def _issue_execution_ticket(entry: dict[str, Any], *, now: float, resolved_by: str) -> str:
    ticket = secrets.token_urlsafe(32)
    entry["execution_ticket_hash"] = _execution_ticket_hash(ticket)
    entry["execution_ticket_issued_at"] = now
    entry["execution_ticket_resolver"] = resolved_by
    return ticket


def _validate_execution_ticket(
    entry: dict[str, Any],
    *,
    ticket: str,
    resolver_id: str,
) -> tuple[bool, str]:
    expected_hash = str(entry.get("execution_ticket_hash", "")).strip()
    if not expected_hash:
        return False, "approval_ticket_missing"
    if not ticket:
        return False, "approval_ticket_required"
    provided_hash = _execution_ticket_hash(ticket)
    if not hmac.compare_digest(expected_hash, provided_hash):
        return False, "approval_ticket_invalid"
    expected_resolver = str(entry.get("execution_ticket_resolver", "")).strip().lower()
    if expected_resolver and not resolver_id:
        return False, "resolver_id_required"
    if expected_resolver and resolver_id != expected_resolver:
        return False, "resolver_mismatch"
    return True, ""


def _expire_pending_approvals(proactive_state: dict[str, Any], *, now: float) -> int:
    queue = _approval_queue(proactive_state)
    expired = 0
    for row in queue:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "pending")).strip().lower() or "pending"
        if status != "pending":
            continue
        expires_at = float(row.get("expires_at", 0.0) or 0.0)
        if expires_at > 0.0 and expires_at <= now:
            row["status"] = "expired"
            row["expired_at"] = now
            expired += 1
    if expired:
        proactive_state["approval_expired_total"] = int(proactive_state.get("approval_expired_total", 0) or 0) + expired
    return expired


def _find_approval(approvals: list[dict[str, Any]], approval_id: str) -> dict[str, Any] | None:
    for row in approvals:
        if not isinstance(row, dict):
            continue
        if str(row.get("approval_id", "")).strip().lower() == approval_id:
            return row
    return None


def _issue_approval_request(
    proactive_state: dict[str, Any],
    *,
    now: float,
    requester_id: str,
    actions: list[dict[str, Any]],
    sensitive_count: int,
    step_up_required: bool,
) -> tuple[dict[str, Any], bool]:
    approvals = _approval_queue(proactive_state)
    fingerprint = _action_fingerprint(actions)
    for row in reversed(approvals):
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "")).strip().lower() != "pending":
            continue
        if str(row.get("requester_id", "")).strip().lower() != requester_id:
            continue
        if str(row.get("actions_fingerprint", "")).strip() != fingerprint:
            continue
        expires_at = float(row.get("expires_at", 0.0) or 0.0)
        if expires_at > 0.0 and expires_at <= now:
            continue
        row["last_requested_at"] = now
        return row, True

    next_seq = int(proactive_state.get("approval_seq", 1) or 1)
    if next_seq < 1:
        next_seq = 1
    approval_id = f"approval-{next_seq}"
    proactive_state["approval_seq"] = next_seq + 1
    created = {
        "approval_id": approval_id,
        "status": "pending",
        "created_at": now,
        "last_requested_at": now,
        "expires_at": now + APPROVAL_TTL_SEC,
        "requester_id": requester_id,
        "risk": "high",
        "tool_name": "home_orchestrator",
        "action": "execute",
        "summary": f"Execute {len(actions)} action(s), sensitive={sensitive_count}",
        "sensitive_action_count": int(max(0, sensitive_count)),
        "actions_count": int(len(actions)),
        "step_up_required": bool(step_up_required),
        "actions": [{**row} for row in actions[:100]],
        "actions_fingerprint": fingerprint,
    }
    approvals.append(created)
    proactive_state["approval_requests_total"] = int(proactive_state.get("approval_requests_total", 0) or 0) + 1
    if len(approvals) > APPROVAL_QUEUE_MAX:
        prune_count = len(approvals) - APPROVAL_QUEUE_MAX
        del approvals[:prune_count]
        proactive_state["approval_pruned_total"] = int(proactive_state.get("approval_pruned_total", 0) or 0) + prune_count
    return created, False


async def home_orch_plan(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _home_plan_from_request = s._home_plan_from_request
    _slugify_identifier = s._slugify_identifier
    SENSITIVE_DOMAINS = s.SENSITIVE_DOMAINS

    request_text = str(args.get("request_text", "")).strip()
    if not request_text:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "request_text is required for plan action."}]}
    plan = _home_plan_from_request(request_text)
    raw_label = str(plan.get("label", "")).strip()
    plan_label = _slugify_identifier(raw_label or request_text[:48], fallback="custom")
    raw_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    steps: list[dict[str, Any]] = []
    seen_steps: set[str] = set()
    skipped_count = 0
    for row in raw_steps[:100]:
        normalized, error = _normalize_action_row(row)
        if normalized is None:
            skipped_count += 1
            continue
        signature = f"{normalized['domain']}:{normalized['action']}:{normalized['entity_id']}"
        if signature in seen_steps:
            continue
        seen_steps.add(signature)
        steps.append(normalized)
    high_impact = [
        row
        for row in steps
        if str(row.get("domain", "")).strip().lower() in SENSITIVE_DOMAINS
    ]
    payload = {
        "action": "plan",
        "request_text": request_text,
        "plan_label": plan_label,
        "step_count": len(steps),
        "steps": steps,
        "skipped_step_count": skipped_count,
        "high_impact_count": len(high_impact),
        "requires_confirmation": bool(high_impact),
    }
    record_summary(
        "home_orchestrator",
        "ok",
        start_time,
        effect=f"plan:{plan_label}:steps={len(steps)}",
        risk="medium" if high_impact else "low",
    )
    return _expansion_payload_response(payload)


async def home_orch_execute(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _as_bool = s._as_bool
    _as_int = s._as_int
    _tool_permitted = s._tool_permitted
    _ha_call_service = s._ha_call_service
    _ha_invalidate_state = s._ha_invalidate_state
    _home_area_policy_violation = s._home_area_policy_violation
    _identity_authorize = s._identity_authorize
    _record_identity_trust_outcome = s._record_identity_trust_outcome
    _validate_step_up_token = s._validate_step_up_token
    _verify_home_action_effect = s._verify_home_action_effect
    _domain_in_policy = s._domain_in_policy
    _config = s._config
    _policy_engine = s._policy_engine
    _proactive_state = s._proactive_state
    SENSITIVE_DOMAINS = s.SENSITIVE_DOMAINS
    policy_engine = _policy_engine if isinstance(_policy_engine, dict) else {}
    execution_policy = (
        policy_engine.get("execution")
        if isinstance(policy_engine.get("execution"), dict)
        else {}
    )
    effect_verification_domains = (
        execution_policy.get("effect_verification_domains")
        if isinstance(execution_policy.get("effect_verification_domains"), list)
        else []
    )
    policy_high_risk_domains = (
        execution_policy.get("high_risk_domains")
        if isinstance(execution_policy.get("high_risk_domains"), list)
        else []
    )
    policy_max_actions = _as_int(
        execution_policy.get("max_actions_per_execute", 25),
        25,
        minimum=1,
        maximum=500,
    )

    now = time.time()
    _expire_pending_approvals(_proactive_state, now=now)
    approvals = _approval_queue(_proactive_state)
    approval_id = str(args.get("approval_id", "")).strip().lower()
    execution_ticket = str(args.get("execution_ticket", "")).strip()
    step_up_token = str(args.get("step_up_token", "")).strip()
    operator_identity = str(args.get("__operator_identity", "")).strip().lower()
    if operator_identity and not operator_identity.startswith(("session-", "token-")):
        operator_identity = ""
    resolver_id = (
        operator_identity
        or str(args.get("resolver_id") or args.get("requester_id") or "").strip().lower()
    )
    approval_entry = _find_approval(approvals, approval_id) if approval_id else None

    raw_actions = args.get("actions")
    if (not isinstance(raw_actions, list) or not raw_actions) and isinstance(approval_entry, dict):
        saved_actions = approval_entry.get("actions")
        if isinstance(saved_actions, list) and saved_actions:
            raw_actions = saved_actions

    if approval_id and not isinstance(approval_entry, dict):
        _record_service_error("home_orchestrator", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Unknown approval_id: {approval_id}."}]}
    if isinstance(approval_entry, dict):
        approval_status = str(approval_entry.get("status", "")).strip().lower()
        if approval_status == "pending":
            _record_service_error("home_orchestrator", start_time, "confirm_required")
            return {"content": [{"type": "text", "text": f"approval_id={approval_id} is still pending operator approval."}]}
        if approval_status == "rejected":
            _record_service_error("home_orchestrator", start_time, "policy")
            return {"content": [{"type": "text", "text": f"approval_id={approval_id} was rejected and cannot be executed."}]}
        if approval_status == "expired":
            _record_service_error("home_orchestrator", start_time, "policy")
            return {"content": [{"type": "text", "text": f"approval_id={approval_id} has expired; request a new approval."}]}
        if approval_status == "consumed":
            _record_service_error("home_orchestrator", start_time, "policy")
            return {"content": [{"type": "text", "text": f"approval_id={approval_id} has already been consumed."}]}
        if approval_status != "approved":
            _record_service_error("home_orchestrator", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": f"approval_id={approval_id} is not executable (status={approval_status})."}]}
    if not isinstance(raw_actions, list) or not raw_actions:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "actions list is required for execute action (or supply approved approval_id)."}]}

    max_actions = _as_int(args.get("max_actions", policy_max_actions), policy_max_actions, minimum=1, maximum=100)
    actions = raw_actions[:max_actions]
    dropped_count = max(0, len(raw_actions) - len(actions))
    confirm = _as_bool(args.get("confirm"), default=False)
    dry_run = _as_bool(args.get("dry_run"), default=not confirm)
    execute_live = not dry_run
    if execute_live and not confirm:
        _record_service_error("home_orchestrator", start_time, "confirm_required")
        return {"content": [{"type": "text", "text": "execute with dry_run=false requires confirm=true."}]}

    normalized_actions = [
        normalized
        for row in actions
        for normalized, _error in [_normalize_action_row(row)]
        if normalized is not None
    ]
    sensitive_count = sum(
        1
        for row in normalized_actions
        if (
            str(row.get("domain", "")).strip().lower() in SENSITIVE_DOMAINS
            or _domain_in_policy(
                policy_high_risk_domains,
                str(row.get("domain", "")).strip().lower(),
            )
        )
    )
    high_risk_live = execute_live and sensitive_count > 0
    step_up_required = any(
        _domain_in_policy(
            (
                policy_engine.get("identity", {}).get("step_up_required_domains", [])
                if isinstance(policy_engine.get("identity"), dict)
                else []
            ),
            str(row.get("domain", "")).strip().lower(),
        )
        for row in normalized_actions
        if isinstance(row, dict)
    )
    if isinstance(approval_entry, dict):
        expected_fingerprint = str(approval_entry.get("actions_fingerprint", "")).strip()
        current_fingerprint = _action_fingerprint(normalized_actions)
        if expected_fingerprint and current_fingerprint != expected_fingerprint:
            _record_service_error("home_orchestrator", start_time, "invalid_data")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "approval_id actions do not match the requested execution payload.",
                    }
                ]
            }
        if execute_live:
            if not operator_identity:
                _record_service_error("home_orchestrator", start_time, "policy")
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "approved execution requires authenticated operator context.",
                        }
                    ]
                }
            resolver_id = operator_identity
            ticket_ok, ticket_reason = _validate_execution_ticket(
                approval_entry,
                ticket=execution_ticket,
                resolver_id=resolver_id,
            )
            if not ticket_ok:
                _record_service_error("home_orchestrator", start_time, "policy")
                reason_text = {
                    "approval_ticket_missing": "approval_id is approved but missing execution ticket metadata; resolve it again.",
                    "approval_ticket_required": "execution_ticket is required for approved high-risk execution.",
                    "approval_ticket_invalid": "execution_ticket is invalid for this approval_id.",
                    "resolver_id_required": "resolver_id is required for approved high-risk execution.",
                    "resolver_mismatch": "resolver_id does not match the approval resolver.",
                }.get(ticket_reason, "approval execution ticket validation failed.")
                return {"content": [{"type": "text", "text": reason_text}]}
            if bool(approval_entry.get("step_up_required", False)):
                approval_scope = str(approval_entry.get("actions_fingerprint", "")).strip() or approval_id
                token_ok, token_reason = _validate_step_up_token(
                    step_up_token,
                    requester_id=resolver_id,
                    domain="home_orchestrator",
                    scope=approval_scope,
                    consume=True,
                )
                if not token_ok:
                    _record_service_error("home_orchestrator", start_time, "policy")
                    reason_text = {
                        "missing": "step_up_token is required for this approved execution.",
                        "not_found": "step_up_token is invalid or expired.",
                        "consumed": "step_up_token has already been consumed.",
                        "requester_mismatch": "step_up_token requester does not match resolver.",
                        "domain_mismatch": "step_up_token scope does not match this domain.",
                        "scope_missing": "step_up_token scope is missing for this approved execution.",
                        "scope_mismatch": "step_up_token scope does not match the approved action set.",
                    }.get(token_reason, "step_up_token validation failed.")
                    return {"content": [{"type": "text", "text": reason_text}]}

    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_orchestrator",
        args,
        mutating=execute_live,
        high_risk=(high_risk_live and not isinstance(approval_entry, dict)),
    )
    if not identity_allowed:
        if high_risk_live and (
            "deny:approval_required" in identity_chain
            or "deny:step_up_required" in identity_chain
        ):
            requester_id = str(identity_context.get("requester_id", "")).strip().lower() or "unknown"
            approval_request, deduped = _issue_approval_request(
                _proactive_state,
                now=now,
                requester_id=requester_id,
                actions=normalized_actions,
                sensitive_count=sensitive_count,
                step_up_required=step_up_required,
            )
            payload = {
                "action": "execute",
                "dry_run": bool(dry_run),
                "confirm": bool(confirm),
                "approval_required": True,
                "approval_id": str(approval_request.get("approval_id", "")),
                "approval_status": str(approval_request.get("status", "")),
                "approval_expires_at": float(approval_request.get("expires_at", 0.0) or 0.0),
                "approval_deduped": deduped,
                "step_up_required": bool(step_up_required),
                "requested_count": len(raw_actions),
                "processed_count": len(actions),
                "dropped_count": dropped_count,
                "sensitive_action_count": sensitive_count,
                "requester_id": requester_id,
                "message": identity_message or "High-risk execution requires approval.",
            }
            record_summary("home_orchestrator", "denied", start_time, effect="execute:approval_required", risk="high")
            return _expansion_payload_response(payload)
        _record_service_error("home_orchestrator", start_time, "policy")
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}

    approval_consumed = False
    if execute_live and isinstance(approval_entry, dict):
        approval_entry["status"] = "consumed"
        approval_entry["consumed_at"] = now
        approval_entry["consumed_by"] = (
            resolver_id
            or str(identity_context.get("requester_id", "")).strip().lower()
            or "unknown"
        )
        approval_entry["execution_ticket_hash"] = ""
        approval_entry["execution_ticket_consumed_at"] = now
        _proactive_state["approval_consumed_total"] = int(_proactive_state.get("approval_consumed_total", 0) or 0) + 1
        approval_consumed = True

    smart_home_allowed = _tool_permitted("smart_home")
    has_home_assistant = bool(_config and _config.has_home_assistant)
    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    live_success_count = 0
    verification_total = 0
    verification_passed = 0
    verification_failed = 0
    for row in actions:
        normalized, error = _normalize_action_row(row)
        if normalized is None:
            results.append({"status": "failed", "reason": error or "invalid_data", "entry": row})
            continue
        domain = str(normalized.get("domain", ""))
        tool_action = str(normalized.get("action", ""))
        entity_id = str(normalized.get("entity_id", ""))
        data = normalized.get("data") if isinstance(normalized.get("data"), dict) else {}
        pair = f"{domain}:{tool_action}:{entity_id}"
        if pair in seen_keys:
            results.append({"status": "failed", "reason": "duplicate_action", "entry": normalized})
            continue
        seen_keys.add(pair)
        blocked, reason = _home_area_policy_violation(
            domain=domain,
            action=tool_action,
            entity_id=entity_id,
            data=data,
        )
        if blocked:
            results.append({"status": "failed", "reason": "area_policy", "detail": reason, "entry": normalized})
            continue
        if execute_live and not smart_home_allowed:
            results.append({"status": "failed", "reason": "policy", "detail": "smart_home execution is not permitted.", "entry": normalized})
            continue
        if execute_live and not has_home_assistant:
            results.append({"status": "failed", "reason": "missing_config", "detail": "Home Assistant is not configured.", "entry": normalized})
            continue
        if not execute_live:
            results.append({"status": "ok", "entry": normalized, "preflight": "passed"})
            continue

        response, error_code = await _ha_call_service(
            domain,
            tool_action,
            {"entity_id": entity_id, **data},
            timeout_sec=10.0,
        )
        if error_code is None:
            live_success_count += 1
            result_row: dict[str, Any] = {"status": "ok", "entry": normalized, "executed": True}
            # Ensure verification observes fresh state after mutation.
            _ha_invalidate_state(entity_id)
            verification = await _verify_home_action_effect(
                domain=domain,
                action=tool_action,
                entity_id=entity_id,
                enabled_domains=effect_verification_domains,
                max_attempts=2,
            )
            # Verification may repopulate cache; clear before next operations.
            _ha_invalidate_state(entity_id)
            result_row["verification"] = verification
            if bool(verification.get("applied", False)):
                verification_total += 1
                _proactive_state["effect_verification_total"] = int(
                    _proactive_state.get("effect_verification_total", 0) or 0
                ) + 1
                if bool(verification.get("verified", False)):
                    verification_passed += 1
                    _proactive_state["effect_verification_passed_total"] = int(
                        _proactive_state.get("effect_verification_passed_total", 0) or 0
                    ) + 1
                else:
                    verification_failed += 1
                    _proactive_state["effect_verification_failed_total"] = int(
                        _proactive_state.get("effect_verification_failed_total", 0) or 0
                    ) + 1
            if isinstance(response, list):
                result_row["response_count"] = len(response)
            results.append(result_row)
            continue
        results.append(
            {
                "status": "failed",
                "reason": "execution_error",
                "error_code": str(error_code),
                "entry": normalized,
            }
        )
    ok_count = sum(1 for item in results if item.get("status") == "ok")
    fail_count = len(results) - ok_count
    payload = {
        "action": "execute",
        "dry_run": bool(dry_run),
        "confirm": bool(confirm),
        "requested_count": len(raw_actions),
        "processed_count": len(actions),
        "dropped_count": dropped_count,
        "executed_count": ok_count,
        "live_executed_count": live_success_count,
        "failed_count": fail_count,
        "sensitive_action_count": sensitive_count,
        "partial_failure": ok_count > 0 and fail_count > 0,
        "effect_verification": {
            "attempted": verification_total,
            "verified": verification_passed,
            "failed": verification_failed,
        },
        "approval_id": approval_id,
        "approval_consumed": approval_consumed,
        "resolver_id": resolver_id,
        "results": results,
    }
    requester_for_trust = str(identity_context.get("requester_id", "")).strip().lower()
    if requester_for_trust and execute_live:
        _record_identity_trust_outcome(
            requester_for_trust,
            success=(fail_count == 0 and verification_failed == 0),
            high_risk=high_risk_live,
            verification_failed=(verification_failed > 0),
        )
    risk = "high" if execute_live and sensitive_count else ("medium" if fail_count or execute_live else "low")
    record_summary(
        "home_orchestrator",
        "ok",
        start_time,
        effect=f"execute_ok={ok_count}_fail={fail_count}_live={live_success_count}",
        risk=risk,
    )
    return _expansion_payload_response(payload)


async def home_orch_approval_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _as_int = s._as_int
    _proactive_state = s._proactive_state

    now = time.time()
    _expire_pending_approvals(_proactive_state, now=now)
    status_filter = str(args.get("status_filter", "all")).strip().lower() or "all"
    if status_filter not in {"all", "pending", "approved", "rejected", "expired", "consumed"}:
        status_filter = "all"
    limit = _as_int(args.get("limit", 25), 25, minimum=1, maximum=200)
    approvals = _approval_queue(_proactive_state)
    sorted_rows = sorted(
        [row for row in approvals if isinstance(row, dict)],
        key=lambda row: float(row.get("created_at", 0.0) or 0.0),
        reverse=True,
    )
    status_counts: dict[str, int] = {}
    filtered: list[dict[str, Any]] = []
    for row in sorted_rows:
        status = str(row.get("status", "pending")).strip().lower() or "pending"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status_filter != "all" and status != status_filter:
            continue
        filtered.append(
            {
                "approval_id": str(row.get("approval_id", "")),
                "status": status,
                "summary": str(row.get("summary", "")),
                "requester_id": str(row.get("requester_id", "")),
                "created_at": float(row.get("created_at", 0.0) or 0.0),
                "expires_at": float(row.get("expires_at", 0.0) or 0.0),
                "resolved_at": float(row.get("resolved_at", 0.0) or 0.0),
                "resolved_by": str(row.get("resolved_by", "")),
                "consumed_at": float(row.get("consumed_at", 0.0) or 0.0),
                "ticket_required": bool(str(row.get("execution_ticket_hash", "")).strip()),
                "ticket_issued_at": float(row.get("execution_ticket_issued_at", 0.0) or 0.0),
                "step_up_required": bool(row.get("step_up_required", False)),
                "step_up_token_issued_at": float(row.get("step_up_token_issued_at", 0.0) or 0.0),
                "step_up_token_expires_at": float(row.get("step_up_token_expires_at", 0.0) or 0.0),
                "actions_count": int(row.get("actions_count", 0) or 0),
                "sensitive_action_count": int(row.get("sensitive_action_count", 0) or 0),
            }
        )
        if len(filtered) >= limit:
            break
    payload = {
        "action": "approval_list",
        "status_filter": status_filter,
        "approval_count": len(sorted_rows),
        "pending_count": status_counts.get("pending", 0),
        "status_counts": status_counts,
        "approvals": filtered,
    }
    record_summary("home_orchestrator", "ok", start_time, effect="approval_list", risk="low")
    return _expansion_payload_response(payload)


async def home_orch_approval_resolve(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _as_bool = s._as_bool
    _issue_step_up_token = s._issue_step_up_token
    _policy_engine = s._policy_engine
    _proactive_state = s._proactive_state
    policy_engine = _policy_engine if isinstance(_policy_engine, dict) else {}
    identity_policy = policy_engine.get("identity") if isinstance(policy_engine.get("identity"), dict) else {}
    step_up_ttl_sec = s._as_float(
        identity_policy.get("step_up_token_ttl_sec", 900.0),
        900.0,
        minimum=30.0,
        maximum=86_400.0,
    )

    approval_id = str(args.get("approval_id", "")).strip().lower()
    if not approval_id:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "approval_id is required for approval_resolve."}]}
    if "approved" not in args:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "approved is required for approval_resolve."}]}
    operator_identity = str(args.get("__operator_identity", "")).strip().lower()
    if not operator_identity or not operator_identity.startswith(("session-", "token-")):
        _record_service_error("home_orchestrator", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "approval_resolve requires authenticated operator context.",
                }
            ]
        }

    now = time.time()
    _expire_pending_approvals(_proactive_state, now=now)
    approvals = _approval_queue(_proactive_state)
    entry = _find_approval(approvals, approval_id)
    if not isinstance(entry, dict):
        _record_service_error("home_orchestrator", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Unknown approval_id: {approval_id}."}]}
    status = str(entry.get("status", "pending")).strip().lower() or "pending"
    approved_requested = _as_bool(args.get("approved"), default=False)
    if status != "pending":
        payload = {
            "action": "approval_resolve",
            "approval_id": approval_id,
            "resolved": False,
            "status": status,
            "reason": "approval_not_pending",
        }
        if status == "approved" and approved_requested:
            current_resolver = str(entry.get("resolved_by", "")).strip().lower()
            if current_resolver and operator_identity != current_resolver:
                payload["reason"] = "resolver_mismatch"
            else:
                resolver_for_ticket = current_resolver or operator_identity
                refreshed_ticket = _issue_execution_ticket(entry, now=now, resolved_by=resolver_for_ticket)
                scope = str(entry.get("actions_fingerprint", "")).strip() or approval_id
                step_up_token_entry = _issue_step_up_token(
                    requester_id=resolver_for_ticket,
                    domain="home_orchestrator",
                    scope=scope,
                    ttl_sec=step_up_ttl_sec,
                )
                entry["step_up_token_issued_at"] = float(step_up_token_entry.get("issued_at", 0.0) or 0.0)
                entry["step_up_token_expires_at"] = float(step_up_token_entry.get("expires_at", 0.0) or 0.0)
                payload.update(
                    {
                        "ticket_refreshed": True,
                        "resolved_by": resolver_for_ticket,
                        "execution_ticket": refreshed_ticket,
                        "step_up_token": str(step_up_token_entry.get("token", "")),
                        "step_up_token_expires_at": float(step_up_token_entry.get("expires_at", 0.0) or 0.0),
                    }
                )
        record_summary("home_orchestrator", "ok", start_time, effect="approval_resolve_noop", risk="low")
        return _expansion_payload_response(payload)

    approved = approved_requested
    resolved_by = operator_identity
    notes = str(args.get("notes", "")).strip()
    entry["status"] = "approved" if approved else "rejected"
    entry["resolved_at"] = now
    entry["resolved_by"] = resolved_by
    entry["notes"] = notes
    execution_ticket = ""
    step_up_token = ""
    if approved:
        execution_ticket = _issue_execution_ticket(entry, now=now, resolved_by=resolved_by)
        scope = str(entry.get("actions_fingerprint", "")).strip() or approval_id
        step_up_token_entry = _issue_step_up_token(
            requester_id=resolved_by,
            domain="home_orchestrator",
            scope=scope,
            ttl_sec=step_up_ttl_sec,
        )
        step_up_token = str(step_up_token_entry.get("token", ""))
        entry["step_up_token_issued_at"] = float(step_up_token_entry.get("issued_at", 0.0) or 0.0)
        entry["step_up_token_expires_at"] = float(step_up_token_entry.get("expires_at", 0.0) or 0.0)
        _proactive_state["approval_approved_total"] = int(_proactive_state.get("approval_approved_total", 0) or 0) + 1
    else:
        entry["execution_ticket_hash"] = ""
        entry["execution_ticket_resolver"] = ""
        entry["execution_ticket_issued_at"] = 0.0
        entry["step_up_token_issued_at"] = 0.0
        entry["step_up_token_expires_at"] = 0.0
        _proactive_state["approval_rejected_total"] = int(_proactive_state.get("approval_rejected_total", 0) or 0) + 1

    payload = {
        "action": "approval_resolve",
        "approval_id": approval_id,
        "resolved": True,
        "approved": approved,
        "status": str(entry.get("status", "")),
        "resolved_by": resolved_by,
        "resolved_at": now,
        "notes": notes,
        "execution_ticket": execution_ticket,
        "step_up_token": step_up_token,
        "step_up_token_expires_at": float(entry.get("step_up_token_expires_at", 0.0) or 0.0),
    }
    record_summary("home_orchestrator", "ok", start_time, effect=f"approval_resolve:{entry['status']}", risk="low")
    return _expansion_payload_response(payload)


async def home_orch_area_policy_set(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _home_area_policies = s._home_area_policies
    _as_str_list = s._as_str_list
    _hhmm_to_minutes = s._hhmm_to_minutes

    area = str(args.get("area", "")).strip().lower()
    policy = args.get("policy") if isinstance(args.get("policy"), dict) else {}
    if not area:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "area is required for area_policy_set."}]}
    quiet_start = str(policy.get("quiet_hours_start", "")).strip()
    quiet_end = str(policy.get("quiet_hours_end", "")).strip()
    if bool(quiet_start) != bool(quiet_end):
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "quiet_hours_start and quiet_hours_end must both be set when configuring quiet hours.",
                }
            ]
        }
    if quiet_start and quiet_end:
        start_minute = _hhmm_to_minutes(quiet_start)
        end_minute = _hhmm_to_minutes(quiet_end)
        if start_minute is None or end_minute is None:
            _record_service_error("home_orchestrator", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "quiet hours must use HH:MM 24-hour format."}]}
        if start_minute == end_minute:
            _record_service_error("home_orchestrator", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "quiet hours start and end cannot be identical."}]}

    blocked_actions = sorted(set(_as_str_list(policy.get("blocked_actions"), lower=True)))
    normalized_blocked: list[str] = []
    invalid_blocked: list[str] = []
    for row in blocked_actions:
        domain, sep, action = row.partition(":")
        if sep and domain.strip() and action.strip():
            normalized_blocked.append(f"{domain.strip()}:{action.strip()}")
        else:
            invalid_blocked.append(row)
    _home_area_policies[area] = {
        "blocked_actions": normalized_blocked,
        "quiet_hours_start": quiet_start,
        "quiet_hours_end": quiet_end,
        "updated_at": time.time(),
    }
    payload = {
        "action": "area_policy_set",
        "area": area,
        "policy": dict(_home_area_policies[area]),
        "policy_count": len(_home_area_policies),
        "invalid_blocked_actions": invalid_blocked,
    }
    record_summary("home_orchestrator", "ok", start_time, effect="area_policy_set", risk="low")
    return _expansion_payload_response(payload)


async def home_orch_area_policy_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _home_area_policies = s._home_area_policies

    area = str(args.get("area", "")).strip().lower()
    if area:
        policy = _home_area_policies.get(area)
        payload = {
            "action": "area_policy_list",
            "area": area,
            "policy": dict(policy) if isinstance(policy, dict) else {},
        }
    else:
        payload = {
            "action": "area_policy_list",
            "policy_count": len(_home_area_policies),
            "policies": {name: dict(row) for name, row in sorted(_home_area_policies.items())},
        }
    record_summary("home_orchestrator", "ok", start_time, effect="area_policy_list", risk="low")
    return _expansion_payload_response(payload)
