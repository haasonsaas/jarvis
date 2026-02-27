"""Identity/trust runtime helpers for services domains."""

from __future__ import annotations

import hmac
from typing import Any


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
        if not (s._as_bool(payload.get("approved"), default=False) or bool(payload.get("approval_code"))):
            chain.append("deny:step_up_required")
            return (
                False,
                f"Trust policy for domain '{domain}' requires step-up approval.",
                context,
                chain,
            )
        chain.append("trust_policy_step_up")
    if high_risk and s._identity_require_approval:
        approved = s._as_bool(payload.get("approved"), default=False)
        approval_code = str(payload.get("approval_code", "")).strip()
        code_valid = bool(s._identity_approval_code) and bool(approval_code) and hmac.compare_digest(
            approval_code,
            s._identity_approval_code,
        )
        trusted_approved = bool(context.get("trusted", False)) and approved
        if not (code_valid or trusted_approved):
            chain.append("deny:approval_required")
            if s._identity_approval_code:
                guidance = "Provide a valid approval_code, or use a trusted requester with approved=true."
            else:
                guidance = "Use a trusted requester with approved=true."
            return (
                False,
                f"High-risk action requires approval. {guidance}",
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
