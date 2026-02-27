"""Validation and identity checks for smart-home mutation preflight."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def home_mutation_policy_validate_identity(
    args: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
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

    return {
        "args": args,
        "domain": domain,
        "action": action,
        "entity_id": entity_id,
        "data": data,
        "dry_run": dry_run,
        "confirm": confirm,
        "safe_mode_forced": safe_mode_forced,
        "identity_context": identity_context,
        "identity_chain": identity_chain,
        "current_state": "unknown",
    }, None
