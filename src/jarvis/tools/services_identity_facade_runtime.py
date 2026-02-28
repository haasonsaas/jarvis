"""Identity helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_identity_runtime import (
    identity_audit_fields as _runtime_identity_audit_fields,
    identity_authorize as _runtime_identity_authorize,
    identity_context as _runtime_identity_context,
    identity_enriched_audit as _runtime_identity_enriched_audit,
    identity_trust_domain as _runtime_identity_trust_domain,
    issue_step_up_token as _runtime_issue_step_up_token,
    record_identity_trust_outcome as _runtime_record_identity_trust_outcome,
    trust_score as _runtime_trust_score,
    validate_step_up_token as _runtime_validate_step_up_token,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def identity_context(args: dict[str, Any] | None) -> dict[str, Any]:
    return _runtime_identity_context(_services_module(), args)


def identity_audit_fields(context: dict[str, Any], decision_chain: list[str] | None = None) -> dict[str, Any]:
    return _runtime_identity_audit_fields(_services_module(), context, decision_chain)


def identity_trust_domain(tool_name: str, args: dict[str, Any] | None) -> str:
    return _runtime_identity_trust_domain(_services_module(), tool_name, args)


def identity_authorize(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    mutating: bool,
    high_risk: bool,
) -> tuple[bool, str | None, dict[str, Any], list[str]]:
    return _runtime_identity_authorize(
        _services_module(),
        tool_name,
        args,
        mutating=mutating,
        high_risk=high_risk,
    )


def identity_enriched_audit(
    details: dict[str, Any],
    identity: dict[str, Any],
    decision_chain: list[str],
) -> dict[str, Any]:
    return _runtime_identity_enriched_audit(
        _services_module(),
        details,
        identity,
        decision_chain,
    )


def issue_step_up_token(
    *,
    requester_id: str,
    domain: str,
    scope: str,
    ttl_sec: float,
) -> dict[str, Any]:
    return _runtime_issue_step_up_token(
        _services_module(),
        requester_id=requester_id,
        domain=domain,
        scope=scope,
        ttl_sec=ttl_sec,
    )


def validate_step_up_token(
    token: str,
    *,
    requester_id: str,
    domain: str,
    scope: str = "",
    consume: bool = False,
) -> tuple[bool, str]:
    return _runtime_validate_step_up_token(
        _services_module(),
        token,
        requester_id=requester_id,
        domain=domain,
        scope=scope,
        consume=consume,
    )


def trust_score(requester_id: str) -> float:
    return _runtime_trust_score(_services_module(), requester_id)


def record_identity_trust_outcome(
    requester_id: str,
    *,
    success: bool,
    high_risk: bool,
    verification_failed: bool = False,
) -> float:
    return _runtime_record_identity_trust_outcome(
        _services_module(),
        requester_id,
        success=success,
        high_risk=high_risk,
        verification_failed=verification_failed,
    )
