"""Integration and identity status snapshot helpers."""

from __future__ import annotations

from typing import Any

def integration_health_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    home_configured = bool(s._config and s._config.has_home_assistant)
    todoist_configured = bool(s._config and str(s._config.todoist_api_token).strip())
    pushover_configured = bool(
        s._config and str(s._config.pushover_api_token).strip() and str(s._config.pushover_user_key).strip()
    )
    return {
        "home_assistant": {
            "configured": home_configured,
            "home_enabled": bool(s._config and s._config.home_enabled),
            "permission_profile": s._home_permission_profile,
            "circuit_breaker": s._integration_circuit_snapshot("home_assistant"),
        },
        "todoist": {
            "configured": todoist_configured,
            "permission_profile": s._todoist_permission_profile,
            "circuit_breaker": s._integration_circuit_snapshot("todoist"),
        },
        "pushover": {
            "configured": pushover_configured,
            "permission_profile": s._notification_permission_profile,
            "circuit_breaker": s._integration_circuit_snapshot("pushover"),
        },
        "weather": {
            "provider": "open-meteo",
            "units_default": s._weather_units,
            "timeout_sec": s._weather_timeout_sec,
            "circuit_breaker": s._integration_circuit_snapshot("weather"),
        },
        "webhook": {
            "allowlist_count": len(s._webhook_allowlist),
            "auth_token_configured": bool(s._webhook_auth_token),
            "timeout_sec": s._webhook_timeout_sec,
            "inbound_events": len(s._inbound_webhook_events),
            "circuit_breaker": s._integration_circuit_snapshot("webhook"),
        },
        "email": {
            "configured": bool(s._email_smtp_host and s._email_from and s._email_default_to),
            "permission_profile": s._email_permission_profile,
            "timeout_sec": s._email_timeout_sec,
            "circuit_breaker": s._integration_circuit_snapshot("email"),
        },
        "channels": {
            "slack_configured": bool(s._slack_webhook_url),
            "discord_configured": bool(s._discord_webhook_url),
            "circuit_breaker": s._integration_circuit_snapshot("channels"),
        },
    }


def identity_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    s._prune_guest_sessions()
    return {
        "enabled": s._identity_enforcement_enabled,
        "default_user": s._identity_default_user,
        "default_profile": s._identity_default_profile,
        "require_approval": s._identity_require_approval,
        "approval_code_configured": bool(s._identity_approval_code),
        "trusted_user_count": len(s._identity_trusted_users),
        "trusted_users": sorted(s._identity_trusted_users),
        "profile_count": len(s._identity_user_profiles),
        "user_profiles": {user: s._identity_user_profiles[user] for user in sorted(s._identity_user_profiles)},
        "trust_policy_count": len(s._identity_trust_policies),
        "trust_policies": {domain: dict(policy) for domain, policy in sorted(s._identity_trust_policies.items())},
        "guest_sessions_active": len(s._guest_sessions),
        "guest_sessions": [
            {
                "guest_id": str(item.get("guest_id", "")),
                "expires_at": float(item.get("expires_at", 0.0) or 0.0),
                "capabilities": s._as_str_list(item.get("capabilities"), lower=True),
            }
            for _, item in sorted(s._guest_sessions.items(), key=lambda pair: str(pair[0]))
        ],
        "household_profile_count": len(s._household_profiles),
        "household_profiles": {user: dict(row) for user, row in sorted(s._household_profiles.items())},
    }


