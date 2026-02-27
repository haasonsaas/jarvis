"""Service policy/routing constants shared across service handlers."""

from __future__ import annotations

SENSITIVE_DOMAINS = {"lock", "alarm_control_panel", "cover", "climate"}

HA_MUTATING_ALLOWED_ACTIONS: dict[str, set[str]] = {
    "light": {"turn_on", "turn_off", "toggle"},
    "switch": {"turn_on", "turn_off", "toggle"},
    "lock": {"lock", "unlock"},
    "cover": {"open_cover", "close_cover", "stop_cover"},
    "climate": {"set_temperature", "set_hvac_mode", "set_fan_mode"},
    "media_player": {
        "turn_on",
        "turn_off",
        "toggle",
        "volume_set",
        "volume_mute",
        "media_play",
        "media_pause",
        "play_media",
    },
    "alarm_control_panel": {"arm_home", "arm_away", "disarm"},
}

INTEGRATION_TOOL_MAP = {
    "smart_home": "home_assistant",
    "smart_home_state": "home_assistant",
    "home_assistant_capabilities": "home_assistant",
    "home_assistant_conversation": "home_assistant",
    "home_assistant_todo": "home_assistant",
    "home_assistant_timer": "home_assistant",
    "home_assistant_area_entities": "home_assistant",
    "media_control": "home_assistant",
    "calendar_events": "home_assistant",
    "calendar_next_event": "home_assistant",
    "todoist_add_task": "todoist",
    "todoist_list_tasks": "todoist",
    "pushover_notify": "pushover",
    "reminder_notify_due": "pushover",
    "weather_lookup": "weather",
    "webhook_trigger": "webhook",
    "slack_notify": "channels",
    "discord_notify": "channels",
    "email_send": "email",
}

SAFE_MODE_BLOCKED_TOOLS = {
    "memory_add",
    "memory_update",
    "memory_forget",
    "memory_summary_add",
    "task_plan_create",
    "task_plan_update",
    "timer_create",
    "timer_cancel",
    "reminder_create",
    "reminder_complete",
    "reminder_notify_due",
}

SENSITIVE_AUDIT_KEY_TOKENS = {
    "code",
    "pin",
    "password",
    "token",
    "secret",
    "alarm_code",
    "passcode",
    "webhook_id",
    "oauth_token",
    "api_key",
    "access_token",
    "authorization",
}

INBOUND_REDACT_HEADER_TOKENS = {
    "authorization",
    "token",
    "cookie",
    "api-key",
    "x-api-key",
    "x-webhook-token",
    "set-cookie",
}

INBOUND_MAX_STRING_CHARS = 4000
INBOUND_MAX_COLLECTION_ITEMS = 120
AUDIT_REDACTED = "***REDACTED***"

AMBIGUOUS_REFERENCE_TERMS = {
    "it",
    "that",
    "this",
    "them",
    "one",
    "something",
    "thing",
    "there",
}

HIGH_RISK_INTENT_TERMS = {
    "unlock",
    "lock",
    "disarm",
    "arm",
    "open",
    "close",
    "disable",
    "enable",
    "delete",
    "send",
    "trigger",
}

EXPLICIT_TARGET_TERMS = {
    "door",
    "garage",
    "gate",
    "alarm",
    "lock",
    "panel",
    "email",
    "message",
    "webhook",
    "light",
    "switch",
    "cover",
    "climate",
    "thermostat",
}

AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS: dict[str, set[str]] = {
    "todoist_add_task": {"content", "description", "due_string", "message", "title"},
    "todoist_list_tasks": {"content", "description", "due_string", "message", "title"},
    "pushover_notify": {"message", "title", "content", "description", "body"},
    "slack_notify": {"message", "title", "content", "description", "body"},
    "discord_notify": {"message", "title", "content", "description", "body"},
    "email_send": {"subject", "body", "content", "description", "message"},
    "home_assistant_conversation": {"text"},
    "reminder_create": {"text"},
    "reminder_list": {"text"},
    "reminder_notify_due": {"text", "message", "title"},
}

MEMORY_SCOPE_TAG_PREFIX = "scope:"
MEMORY_SCOPES = {"preferences", "people", "projects", "household_rules"}
MEMORY_QUERY_SCOPE_HINTS: dict[str, set[str]] = {
    "people": {"who", "person", "people", "contact", "name", "family"},
    "projects": {"project", "projects", "task", "deadline", "repo", "sprint", "milestone"},
    "household_rules": {"home", "house", "rule", "rules", "quiet", "bedtime", "routine", "thermostat"},
}

AUDIT_REASON_MESSAGES: dict[str, str] = {
    "policy": "blocked by global tool policy configuration",
    "identity_policy": "blocked by identity and trust policy",
    "strict_confirm_required": "blocked because strict confirmation is required before execution",
    "sensitive_confirm_required": "blocked because sensitive actions require explicit confirm=true",
    "confirm_required": "blocked because explicit confirmation is required",
    "ambiguous_target": "blocked because the target is ambiguous for a high-risk action",
    "ambiguous_high_risk_text": "blocked because the request text is ambiguous for a high-risk action",
    "area_policy": "blocked by area-level policy constraints",
    "conversation_disabled": "blocked because Home Assistant conversation mode is disabled",
    "conversation_readonly_profile": "blocked because conversation integration is configured as read-only",
    "readonly_profile": "blocked because requester profile is read-only for mutating actions",
    "https_required": "blocked because webhook targets must use HTTPS",
    "allowlist": "blocked because webhook host is outside WEBHOOK_ALLOWLIST",
    "pushover_policy": "blocked because notification policy disables Pushover delivery",
    "safe_mode": "blocked because safe mode disables mutating actions",
    "network_client_error": "failed due to network connectivity error",
    "timeout": "failed because the upstream integration timed out",
    "cancelled": "failed because the request was cancelled before completion",
    "http_error": "failed because the upstream returned an HTTP error",
    "api_error": "failed because the upstream returned an API-level error",
    "auth": "failed because upstream authentication was rejected",
    "unexpected": "failed because an unexpected runtime error occurred",
    "missing_config": "failed because required integration configuration is missing",
    "missing_fields": "failed because required request fields are missing",
    "invalid_data": "failed because provided request data is invalid",
    "invalid_json": "failed because upstream returned invalid JSON",
}
