"""Smart-home mutation preflight and policy checks."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_mutation_prepare(args: dict[str, Any], *, start_time: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    HA_MUTATING_ALLOWED_ACTIONS = s.HA_MUTATING_ALLOWED_ACTIONS
    _ha_action_allowed = s._ha_action_allowed
    _as_bool = s._as_bool
    SENSITIVE_DOMAINS = s.SENSITIVE_DOMAINS
    _safe_mode_enabled = s._safe_mode_enabled
    _identity_authorize = s._identity_authorize
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _redact_sensitive_for_audit = s._redact_sensitive_for_audit
    _home_require_confirm_execute = s._home_require_confirm_execute
    _is_ambiguous_entity_target = s._is_ambiguous_entity_target
    _home_area_policy_violation = s._home_area_policy_violation
    _preview_gate = s._preview_gate
    _cooldown_active = s._cooldown_active
    _ha_get_state = s._ha_get_state

    from jarvis.tools.robot import tool_feedback

    domain = str(args.get("domain", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    data = args.get("data", {})
    if not domain or not entity_id:
        _record_service_error("smart_home", start_time, "missing_fields")
        return None, {"content": [{"type": "text", "text": "Domain and entity_id are required."}]}
    if not action or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in action):
        _record_service_error("smart_home", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": "Action must be a non-empty snake_case service name."}]}
    if not isinstance(data, dict):
        _record_service_error("smart_home", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": "Service data must be an object."}]}
    if domain not in HA_MUTATING_ALLOWED_ACTIONS:
        _record_service_error("smart_home", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": f"Unsupported domain for smart_home: {domain}"}]}
    entity_domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    if not entity_domain or entity_domain != domain:
        _record_service_error("smart_home", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": "entity_id domain must match domain."}]}
    if not _ha_action_allowed(domain, action):
        _record_service_error("smart_home", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": f"Unsupported action for domain: {domain}.{action}"}]}
    dry_run = _as_bool(args.get("dry_run"), default=domain in SENSITIVE_DOMAINS)
    confirm = _as_bool(args.get("confirm"), default=False)
    safe_mode_forced = _safe_mode_enabled and not dry_run
    if safe_mode_forced:
        dry_run = True
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "smart_home",
        args,
        mutating=not dry_run,
        high_risk=(not dry_run and domain in SENSITIVE_DOMAINS),
    )
    if not identity_allowed:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "data": _redact_sensitive_for_audit(data),
                    "dry_run": dry_run,
                    "confirm": confirm,
                    "safe_mode_forced": safe_mode_forced,
                    "state": "unknown",
                    "policy_decision": "denied",
                    "reason": "identity_policy",
                },
                identity_context,
                identity_chain,
            ),
        )
        return None, {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_require_confirm_execute and not dry_run and not confirm:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "data": _redact_sensitive_for_audit(data),
                    "dry_run": dry_run,
                    "confirm": confirm,
                    "safe_mode_forced": safe_mode_forced,
                    "state": "unknown",
                    "policy_decision": "denied",
                    "reason": "strict_confirm_required",
                },
                identity_context,
                [*identity_chain, "deny:strict_confirm_required"],
            ),
        )
        return None, {"content": [{"type": "text", "text": "Action requires confirm=true when HOME_REQUIRE_CONFIRM_EXECUTE=true."}]}
    if domain in SENSITIVE_DOMAINS and not dry_run and not confirm:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "data": _redact_sensitive_for_audit(data),
                    "dry_run": dry_run,
                    "confirm": confirm,
                    "safe_mode_forced": safe_mode_forced,
                    "state": "unknown",
                    "policy_decision": "denied",
                    "reason": "sensitive_confirm_required",
                },
                identity_context,
                [*identity_chain, "deny:sensitive_confirm_required"],
            ),
        )
        return None, {"content": [{"type": "text", "text": "Sensitive action requires confirm=true when dry_run=false."}]}
    if domain in SENSITIVE_DOMAINS and not dry_run and _is_ambiguous_entity_target(entity_id):
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "policy_decision": "denied",
                    "reason": "ambiguous_target",
                },
                identity_context,
                [*identity_chain, "deny:ambiguous_target"],
            ),
        )
        return (
            None,
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Ambiguous high-risk target. Specify one explicit entity instead of a broad/group target.",
                    }
                ]
            },
        )
    if not dry_run:
        area_blocked, area_reason = _home_area_policy_violation(
            domain=domain,
            action=action,
            entity_id=entity_id,
            data=data,
        )
        if area_blocked:
            _record_service_error("smart_home", start_time, "policy")
            _audit(
                "smart_home",
                _identity_enriched_audit(
                    {
                        "domain": domain,
                        "action": action,
                        "entity_id": entity_id,
                        "policy_decision": "denied",
                        "reason": "area_policy",
                        "detail": area_reason,
                    },
                    identity_context,
                    [*identity_chain, "deny:area_policy"],
                ),
            )
            return None, {"content": [{"type": "text", "text": area_reason}]}
    if not dry_run:
        preview_risk = "high" if domain in SENSITIVE_DOMAINS else "medium"
        preview = _preview_gate(
            tool_name="smart_home",
            args=args,
            risk=preview_risk,
            summary=f"{domain}.{action} on {entity_id}",
            signature_payload={
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "data": _redact_sensitive_for_audit(data),
            },
            enforce_default=s._plan_preview_require_ack,
        )
        if preview:
            record_summary("smart_home", "dry_run", start_time, effect="plan_preview", risk=preview_risk)
            _audit(
                "smart_home",
                _identity_enriched_audit(
                    {
                        "domain": domain,
                        "action": action,
                        "entity_id": entity_id,
                        "policy_decision": "preview_required",
                    },
                    identity_context,
                    [*identity_chain, "decision:preview_required"],
                ),
            )
            return None, {"content": [{"type": "text", "text": preview}]}

    current_state = "unknown"
    if not dry_run:
        if _cooldown_active(domain, action, entity_id):
            tool_feedback("done")
            record_summary("smart_home", "cooldown", start_time)
            return None, {"content": [{"type": "text", "text": "Action cooldown active. Try again in a moment."}]}

        state_payload, state_error = await _ha_get_state(entity_id)
        if state_error is not None:
            _record_service_error("smart_home", start_time, state_error)
            if state_error == "not_found":
                return None, {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
            if state_error == "auth":
                return None, {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if state_error == "timeout":
                return None, {"content": [{"type": "text", "text": "Home Assistant state preflight timed out."}]}
            if state_error == "cancelled":
                return None, {"content": [{"type": "text", "text": "Home Assistant state preflight was cancelled."}]}
            if state_error == "circuit_open":
                return None, {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if state_error == "network_client_error":
                return None, {"content": [{"type": "text", "text": "Failed to reach Home Assistant for state preflight."}]}
            return None, {"content": [{"type": "text", "text": "Unable to validate entity state before action."}]}

        current_state = str(state_payload.get("state", "unknown")) if isinstance(state_payload, dict) else "unknown"
        if action == "turn_on" and current_state not in {"off", "unavailable", "unknown"}:
            record_summary("smart_home", "noop", start_time, effect=f"already_on {entity_id}", risk="low")
            return None, {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}
        if action == "turn_off" and current_state == "off":
            record_summary("smart_home", "noop", start_time, effect=f"already_off {entity_id}", risk="low")
            return None, {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}

    return {
        "domain": domain,
        "action": action,
        "entity_id": entity_id,
        "data": data,
        "dry_run": dry_run,
        "confirm": confirm,
        "safe_mode_forced": safe_mode_forced,
        "identity_context": identity_context,
        "identity_chain": identity_chain,
        "current_state": current_state,
    }, None
