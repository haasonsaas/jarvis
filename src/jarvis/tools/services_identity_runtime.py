"""Identity/trust runtime helpers for services domains."""

from __future__ import annotations

import hmac
import secrets
import time
from typing import Any


def _identity_trust_scores(services_module: Any) -> dict[str, float]:
    s = services_module
    row = s._proactive_state.get("identity_trust_scores")
    if isinstance(row, dict):
        return row
    row = {}
    s._proactive_state["identity_trust_scores"] = row
    return row


def trust_score(services_module: Any, requester_id: str) -> float:
    s = services_module
    user = str(requester_id or "").strip().lower()
    if not user:
        return 0.5
    scores = _identity_trust_scores(s)
    return s._as_float(scores.get(user, 0.5), 0.5, minimum=0.0, maximum=1.0)


def record_identity_trust_outcome(
    services_module: Any,
    requester_id: str,
    *,
    success: bool,
    high_risk: bool,
    verification_failed: bool = False,
) -> float:
    s = services_module
    user = str(requester_id or "").strip().lower()
    if not user:
        return 0.5
    scores = _identity_trust_scores(s)
    current = trust_score(s, user)
    if success:
        delta = 0.03 + (0.01 if high_risk else 0.0)
    else:
        delta = -0.08 - (0.04 if high_risk else 0.0)
    if verification_failed:
        delta -= 0.05
    updated = min(1.0, max(0.0, current + delta))
    scores[user] = updated
    return updated


def _prune_step_up_tokens(services_module: Any, *, now: float | None = None) -> None:
    s = services_module
    tokens = s._identity_step_up_tokens
    if not isinstance(tokens, dict):
        s._identity_step_up_tokens = {}
        return
    current_time = float(now if now is not None else time.time())
    stale_keys = [
        key
        for key, row in tokens.items()
        if not isinstance(row, dict)
        or s._as_float(row.get("expires_at", 0.0), 0.0, minimum=0.0) <= current_time
    ]
    for key in stale_keys:
        tokens.pop(key, None)


def issue_step_up_token(
    services_module: Any,
    *,
    requester_id: str,
    domain: str,
    scope: str,
    ttl_sec: float,
) -> dict[str, Any]:
    s = services_module
    now = time.time()
    _prune_step_up_tokens(s, now=now)
    token = secrets.token_urlsafe(24)
    entry = {
        "token": token,
        "requester_id": str(requester_id or "").strip().lower(),
        "domain": str(domain or "").strip().lower(),
        "scope": str(scope or "").strip().lower(),
        "issued_at": now,
        "expires_at": now + s._as_float(ttl_sec, 900.0, minimum=30.0, maximum=86_400.0),
        "consumed": False,
        "consumed_at": 0.0,
    }
    s._identity_step_up_tokens[token] = entry
    if len(s._identity_step_up_tokens) > 1000:
        oldest = sorted(
            s._identity_step_up_tokens.items(),
            key=lambda pair: s._as_float(
                pair[1].get("issued_at", 0.0) if isinstance(pair[1], dict) else 0.0,
                0.0,
                minimum=0.0,
            ),
        )[: len(s._identity_step_up_tokens) - 1000]
        for key, _ in oldest:
            s._identity_step_up_tokens.pop(key, None)
    return entry


def validate_step_up_token(
    services_module: Any,
    token: str,
    *,
    requester_id: str,
    domain: str,
    scope: str = "",
    consume: bool = False,
) -> tuple[bool, str]:
    s = services_module
    token_text = str(token or "").strip()
    if not token_text:
        return False, "missing"
    _prune_step_up_tokens(s)
    entry = s._identity_step_up_tokens.get(token_text)
    if not isinstance(entry, dict):
        return False, "not_found"
    if bool(entry.get("consumed", False)):
        return False, "consumed"
    expected_requester = str(entry.get("requester_id", "")).strip().lower()
    expected_domain = str(entry.get("domain", "")).strip().lower()
    expected_scope = str(entry.get("scope", "")).strip().lower()
    provided_scope = str(scope or "").strip().lower()
    if expected_requester and expected_requester != str(requester_id or "").strip().lower():
        return False, "requester_mismatch"
    if expected_domain and expected_domain != str(domain or "").strip().lower():
        return False, "domain_mismatch"
    if expected_scope and provided_scope and expected_scope != provided_scope:
        return False, "scope_mismatch"
    if expected_scope and not provided_scope:
        return False, "scope_missing"
    if consume:
        entry["consumed"] = True
        entry["consumed_at"] = time.time()
    return True, ""


def identity_context(services_module: Any, args: dict[str, Any] | None) -> dict[str, Any]:
    s = services_module
    payload = args if isinstance(args, dict) else {}
    request_context = payload.get("request_context")
    context_payload = request_context if isinstance(request_context, dict) else {}
    guest_token = str(
        payload.get("guest_session_token")
        or context_payload.get("guest_session_token")
        or ""
    ).strip()
    guest_session = s._resolve_guest_session(guest_token) if guest_token else None

    if guest_session is not None:
        speaker_verified = s._as_bool(
            payload.get("speaker_verified", context_payload.get("speaker_verified")),
            default=False,
        )
        return {
            "requester_id": str(guest_session.get("guest_id", "guest")),
            "profile": "guest",
            "trusted": False,
            "speaker_verified": speaker_verified,
            "source": "guest_session",
            "guest_session_token": str(guest_session.get("token", "")),
            "guest_capabilities": s._as_str_list(guest_session.get("capabilities"), lower=True),
            "guest_expires_at": float(guest_session.get("expires_at", 0.0) or 0.0),
        }

    requester_id = str(payload.get("requester_id", "")).strip().lower()
    source = "requester_id"
    if not requester_id:
        requester_id = str(context_payload.get("requester_id") or context_payload.get("user_id") or "").strip().lower()
        source = "request_context" if requester_id else "default"
    if not requester_id:
        requester_id = s._identity_default_user
    profile = s._identity_user_profiles.get(requester_id, s._identity_default_profile)
    if profile not in {"deny", "readonly", "control", "trusted"}:
        profile = "control"
    speaker_verified = s._as_bool(
        payload.get("speaker_verified", context_payload.get("speaker_verified")),
        default=False,
    )
    trusted = requester_id in s._identity_trusted_users or profile == "trusted" or speaker_verified
    return {
        "requester_id": requester_id,
        "profile": s._identity_profile_level(profile),
        "trusted": trusted,
        "speaker_verified": speaker_verified,
        "source": source,
        "guest_session_token": "",
        "guest_capabilities": [],
        "guest_expires_at": 0.0,
    }


def identity_audit_fields(
    services_module: Any,
    context: dict[str, Any],
    decision_chain: list[str] | None = None,
) -> dict[str, Any]:
    s = services_module
    chain = [str(item) for item in (decision_chain or []) if str(item).strip()]
    if not chain:
        chain = ["identity_context_applied"]
    return {
        "requester_id": str(context.get("requester_id", "")),
        "requester_profile": s._identity_profile_level(str(context.get("profile", "control"))),
        "requester_trusted": bool(context.get("trusted", False)),
        "speaker_verified": bool(context.get("speaker_verified", False)),
        "identity_source": str(context.get("source", "default")),
        "guest_session_token": str(context.get("guest_session_token", "")),
        "guest_expires_at": float(context.get("guest_expires_at", 0.0) or 0.0),
        "decision_chain": chain,
    }


def identity_trust_domain(services_module: Any, tool_name: str, args: dict[str, Any] | None) -> str:
    payload = args if isinstance(args, dict) else {}
    domain = str(payload.get("domain", "")).strip().lower()
    if domain:
        return domain
    mapped = {
        "email_send": "email",
        "webhook_trigger": "webhook",
        "slack_notify": "messaging",
        "discord_notify": "messaging",
        "home_assistant_conversation": "home_assistant",
        "smart_home": "home_assistant",
        "home_orchestrator": "home_orchestrator",
        "media_control": "home_assistant",
        "todoist_add_task": "todoist",
    }
    return mapped.get(str(tool_name or "").strip().lower(), "general")


def identity_authorize(
    services_module: Any,
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    mutating: bool,
    high_risk: bool,
) -> tuple[bool, str | None, dict[str, Any], list[str]]:
    s = services_module
    context = identity_context(s, args)
    payload = args if isinstance(args, dict) else {}
    chain = [
        f"tool={tool_name}",
        f"requester={context['requester_id']}",
        f"profile={context['profile']}",
    ]
    if s._safe_mode_enabled and mutating:
        chain.append("deny:safe_mode")
        return (
            False,
            "Safe mode is enabled. Mutating actions are blocked; disable safe mode or use dry-run where supported.",
            context,
            chain,
        )
    if s._identity_profile_level(str(context.get("profile", "control"))) == "guest":
        guest_caps = {
            item
            for item in s._as_str_list(context.get("guest_capabilities"), lower=True)
            if item
        }
        tool_cap = str(tool_name or "").strip().lower()
        if tool_cap not in guest_caps and "*" not in guest_caps:
            chain.append("deny:guest_capability")
            return (
                False,
                f"Guest session does not allow '{tool_name}'. Allowed capabilities: {sorted(guest_caps)}",
                context,
                chain,
            )
        chain.append("guest_session_capability")

    if not s._identity_enforcement_enabled:
        chain.append("identity_enforcement_disabled")
        return True, None, context, chain

    profile = s._identity_profile_level(str(context.get("profile", "control")))
    requester_id = str(context.get("requester_id", "")).strip().lower()
    trust_score_value = trust_score(s, requester_id)
    chain.append(f"trust_score={trust_score_value:.2f}")
    if profile == "deny":
        chain.append("deny:user_profile")
        return (
            False,
            (
                f"Action blocked for requester '{context['requester_id']}'. "
                "Ask an admin to update IDENTITY_USER_PROFILES for this user."
            ),
            context,
            chain,
        )
    if mutating and profile == "readonly":
        chain.append("deny:readonly_profile")
        return (
            False,
            (
                f"Requester '{context['requester_id']}' is readonly for mutating actions. "
                "Ask a trusted user or admin to execute this action."
            ),
            context,
            chain,
        )
    domain = identity_trust_domain(s, tool_name, payload)
    policy_engine = s._policy_engine if isinstance(s._policy_engine, dict) else {}
    identity_policy = policy_engine.get("identity") if isinstance(policy_engine.get("identity"), dict) else {}
    execution_policy = policy_engine.get("execution") if isinstance(policy_engine.get("execution"), dict) else {}
    policy = s._identity_trust_policies.get(domain, {})
    required_profile = s._identity_profile_level(str(policy.get("required_profile", "control")))
    if s._profile_rank(profile) < s._profile_rank(required_profile):
        chain.append("deny:trust_policy")
        return (
            False,
            (
                f"Trust policy for domain '{domain}' requires profile>={required_profile}; "
                f"requester profile is {profile}."
            ),
            context,
            chain,
        )
    if s._as_bool(policy.get("requires_step_up"), default=False):
        step_up_token = str(payload.get("step_up_token", "")).strip()
        step_up_valid, _ = validate_step_up_token(
            s,
            step_up_token,
            requester_id=requester_id,
            domain=domain,
            scope="",
            consume=False,
        )
        if not (
            s._as_bool(payload.get("approved"), default=False)
            or bool(payload.get("approval_code"))
            or step_up_valid
        ):
            chain.append("deny:step_up_required")
            return (
                False,
                f"Trust policy for domain '{domain}' requires step-up approval.",
                context,
                chain,
            )
        if step_up_valid:
            chain.append("step_up_token_valid")
        chain.append("trust_policy_step_up")
    if high_risk and s._identity_require_approval:
        approved = s._as_bool(payload.get("approved"), default=False)
        approval_code = str(payload.get("approval_code", "")).strip()
        step_up_token = str(payload.get("step_up_token", "")).strip()
        step_up_valid, _step_up_reason = validate_step_up_token(
            s,
            step_up_token,
            requester_id=requester_id,
            domain=domain,
            scope="",
            consume=False,
        )
        min_trust_for_high_risk = s._as_float(
            identity_policy.get("min_trust_score_for_high_risk", 0.6),
            0.6,
            minimum=0.0,
            maximum=1.0,
        )
        step_up_domains = (
            identity_policy.get("step_up_required_domains")
            if isinstance(identity_policy.get("step_up_required_domains"), list)
            else []
        )
        execution_high_risk_domains = (
            execution_policy.get("high_risk_domains")
            if isinstance(execution_policy.get("high_risk_domains"), list)
            else []
        )
        step_up_required = s._domain_in_policy(step_up_domains, domain) or s._domain_in_policy(
            execution_high_risk_domains, domain
        )
        code_valid = bool(s._identity_approval_code) and bool(approval_code) and hmac.compare_digest(
            approval_code,
            s._identity_approval_code,
        )
        trusted_approved = bool(context.get("trusted", False)) and approved
        low_trust = trust_score_value < min_trust_for_high_risk
        chain.append(f"step_up_required={step_up_required}")
        chain.append(f"low_trust={low_trust}")
        if step_up_valid:
            chain.append("step_up_token_valid")
        approval_ok = code_valid or trusted_approved or step_up_valid
        if not approval_ok:
            chain.append("deny:approval_required")
            if s._identity_approval_code:
                guidance = (
                    "Provide a valid approval_code, use a trusted requester with approved=true, "
                    "or provide a valid step_up_token."
                )
            else:
                guidance = "Use a trusted requester with approved=true, or provide a valid step_up_token."
            return (
                False,
                f"High-risk action requires approval. {guidance}",
                context,
                chain,
            )
        if step_up_required or low_trust:
            # High-risk low-trust paths require replay-resistant proof (code or step-up token),
            # not just trusted+approved in-band flags.
            if not (step_up_valid or code_valid):
                chain.append("deny:step_up_required")
                chain.append("deny:trusted_approval_insufficient")
                requirement = "step_up_token or approval_code"
                if s._identity_approval_code:
                    requirement = "step_up_token or valid approval_code"
                return (
                    False,
                    (
                        f"High-risk action for domain '{domain}' requires {requirement} "
                        f"(trust_score={trust_score_value:.2f})."
                    ),
                    context,
                    chain,
                )
        if code_valid:
            chain.append("approval_code_valid")
        if trusted_approved:
            chain.append("trusted_approval")
    if context.get("trusted"):
        chain.append("trusted_requester")
    chain.append("allow")
    return True, None, context, chain


def identity_enriched_audit(
    services_module: Any,
    details: dict[str, Any],
    identity: dict[str, Any],
    decision_chain: list[str],
) -> dict[str, Any]:
    return {**details, **identity_audit_fields(services_module, identity, decision_chain)}
