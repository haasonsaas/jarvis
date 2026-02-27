"""Guardrail checks for smart-home mutation preflight."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_mutation_policy_apply_guardrails(
    context: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    SENSITIVE_DOMAINS = s.SENSITIVE_DOMAINS
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _redact_sensitive_for_audit = s._redact_sensitive_for_audit
    _is_ambiguous_entity_target = s._is_ambiguous_entity_target
    _home_area_policy_violation = s._home_area_policy_violation
    _preview_gate = s._preview_gate

    args = context.get("args") if isinstance(context.get("args"), dict) else {}
    domain = str(context.get("domain", "")).strip().lower()
    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()
    data = context.get("data") if isinstance(context.get("data"), dict) else {}
    dry_run = bool(context.get("dry_run", False))
    identity_context = context.get("identity_context")
    identity_chain = context.get("identity_chain") if isinstance(context.get("identity_chain"), list) else []

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

    context.pop("args", None)
    return context, None
