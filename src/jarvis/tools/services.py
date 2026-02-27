"""External service tools: smart home, weather, etc.

All destructive actions require confirmation (dry-run by default).
Everything is audit-logged.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import random
import re
import secrets
import smtplib
import time
from contextlib import suppress
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
from claude_agent_sdk import tool, create_sdk_mcp_server

from jarvis.config import Config
from jarvis.skills import SkillRegistry
from jarvis.tool_policy import is_tool_allowed
from jarvis.tool_summary import record_summary, list_summaries
from jarvis.memory import MemoryEntry, MemoryStore
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES, normalize_service_error_code

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency fallback
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Audit log in user's home dir for predictable location
AUDIT_LOG = Path.home() / ".jarvis" / "audit.jsonl"
DEFAULT_RECOVERY_JOURNAL = Path.home() / ".jarvis" / "recovery-journal.jsonl"

# Domains that always default to dry_run
SENSITIVE_DOMAINS = {"lock", "alarm_control_panel", "cover", "climate"}
ACTION_COOLDOWN_SEC = 2.0
ACTION_HISTORY_RETENTION_SEC = 3600.0
ACTION_HISTORY_MAX_ENTRIES = 2000
HA_STATE_CACHE_TTL_SEC = 2.0
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
TODOIST_LIST_MAX_RETRIES = 2
RETRY_BASE_DELAY_SEC = 0.2
RETRY_MAX_DELAY_SEC = 1.0
RETRY_JITTER_RATIO = 0.2
SYSTEM_STATUS_CONTRACT_VERSION = "1.7"
HA_CONVERSATION_MAX_TEXT_CHARS = 600
TIMER_MAX_SECONDS = 86_400.0
TIMER_MAX_ACTIVE = 200
REMINDER_MAX_ACTIVE = 500
CALENDAR_DEFAULT_WINDOW_HOURS = 24.0
CALENDAR_MAX_WINDOW_HOURS = 24.0 * 31.0
PLAN_PREVIEW_TTL_SEC = 300.0
PLAN_PREVIEW_MAX_PENDING = 1000
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_BASE_COOLDOWN_SEC = 15.0
CIRCUIT_BREAKER_MAX_COOLDOWN_SEC = 300.0
CIRCUIT_BREAKER_ERROR_CODES = {
    "timeout",
    "cancelled",
    "network_client_error",
    "http_error",
    "api_error",
    "auth",
    "unexpected",
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
_DURATION_SEGMENT_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)",
    re.IGNORECASE,
)
_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # payment-card-like sequence
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # phone-like sequence
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),  # email
]

_config: Config | None = None
_memory: MemoryStore | None = None
_action_last_seen: dict[str, float] = {}
_tool_allowlist: list[str] = []
_tool_denylist: list[str] = []
_audit_log_max_bytes: int = 1_000_000
_audit_log_backups: int = 3
_home_permission_profile: str = "control"
_home_require_confirm_execute: bool = False
_home_conversation_enabled: bool = False
_home_conversation_permission_profile: str = "readonly"
_todoist_permission_profile: str = "control"
_notification_permission_profile: str = "allow"
_nudge_policy: str = "adaptive"
_nudge_quiet_hours_start: str = "22:00"
_nudge_quiet_hours_end: str = "07:00"
_email_permission_profile: str = "readonly"
_todoist_timeout_sec: float = 10.0
_pushover_timeout_sec: float = 10.0
_email_smtp_host: str = ""
_email_smtp_port: int = 587
_email_smtp_username: str = ""
_email_smtp_password: str = ""
_email_from: str = ""
_email_default_to: str = ""
_email_use_tls: bool = True
_email_timeout_sec: float = 10.0
_weather_units: str = "metric"
_weather_timeout_sec: float = 8.0
_webhook_allowlist: list[str] = []
_webhook_auth_token: str = ""
_webhook_timeout_sec: float = 8.0
_turn_timeout_listen_sec: float = 30.0
_turn_timeout_think_sec: float = 60.0
_turn_timeout_speak_sec: float = 45.0
_turn_timeout_act_sec: float = 30.0
_slack_webhook_url: str = ""
_discord_webhook_url: str = ""
_identity_enforcement_enabled: bool = False
_identity_default_user: str = "owner"
_identity_default_profile: str = "control"
_identity_user_profiles: dict[str, str] = {}
_identity_trusted_users: set[str] = set()
_identity_require_approval: bool = True
_identity_approval_code: str = ""
_plan_preview_require_ack: bool = False
_safe_mode_enabled: bool = False
_memory_retention_days: float = 0.0
_audit_retention_days: float = 0.0
_memory_pii_guardrails_enabled: bool = True
_audit_encryption_enabled: bool = False
_data_encryption_key: str = ""
_audit_fernet: Fernet | None = None
_ha_state_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_timers: dict[int, dict[str, Any]] = {}
_timer_id_seq: int = 1
_reminders: dict[int, dict[str, Any]] = {}
_reminder_id_seq: int = 1
_email_history: list[dict[str, Any]] = []
_runtime_voice_state: dict[str, Any] = {}
_runtime_observability_state: dict[str, Any] = {}
_runtime_skills_state: dict[str, Any] = {}
_skill_registry: SkillRegistry | None = None
_inbound_webhook_events: list[dict[str, Any]] = []
_inbound_webhook_seq: int = 1
_pending_plan_previews: dict[str, dict[str, Any]] = {}
_integration_circuit_breakers: dict[str, dict[str, Any]] = {}
_recovery_journal_path: Path = DEFAULT_RECOVERY_JOURNAL
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

SERVICE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "smart_home": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "HA domain: light, switch, climate, media_player, lock, cover, etc.",
            },
            "action": {
                "type": "string",
                "description": "Service to call: turn_on, turn_off, toggle, set_temperature, etc.",
            },
            "entity_id": {
                "type": "string",
                "description": "Entity ID, e.g. light.living_room, climate.thermostat.",
            },
            "data": {
                "type": "object",
                "description": "Optional service data (brightness, temperature, etc.).",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, describe what would happen without executing. "
                "Always true for locks/alarms/covers unless user explicitly confirms.",
            },
            "confirm": {"type": "boolean", "description": "Optional explicit confirmation for execute paths."},
            "requester_id": {"type": "string", "description": "Requester identity for policy decisions and audit."},
            "request_context": {"type": "object", "description": "Optional voice/text context with requester metadata."},
            "speaker_verified": {"type": "boolean", "description": "Trusted-speaker hook for voice identity pipelines."},
            "approved": {"type": "boolean", "description": "Trusted approval handshake flag for high-risk actions."},
            "approval_code": {"type": "string", "description": "Approval code for high-risk actions when required."},
            "preview_only": {"type": "boolean", "description": "Return plan preview without executing."},
            "preview_token": {"type": "string", "description": "Plan preview token required when preview acknowledgment is enforced."},
            "require_preview_ack": {"type": "boolean", "description": "If true, require preview_token before execution."},
        },
        "required": ["domain", "action", "entity_id"],
    },
    "smart_home_state": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
        },
        "required": ["entity_id"],
    },
    "home_assistant_capabilities": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "include_services": {"type": "boolean"},
        },
        "required": ["entity_id"],
    },
    "home_assistant_conversation": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Natural language command for HA conversation agent."},
            "language": {"type": "string", "description": "Optional language code (for example en)."},
            "agent_id": {"type": "string", "description": "Optional Home Assistant conversation agent id."},
            "confirm": {
                "type": "boolean",
                "description": "Must be true for execution to reduce accidental high-impact voice commands.",
            },
            "requester_id": {"type": "string", "description": "Requester identity for policy decisions and audit."},
            "request_context": {"type": "object", "description": "Optional voice/text context with requester metadata."},
            "speaker_verified": {"type": "boolean", "description": "Trusted-speaker hook for voice identity pipelines."},
            "approved": {"type": "boolean", "description": "Trusted approval handshake flag for high-risk actions."},
            "approval_code": {"type": "string", "description": "Approval code for high-risk actions when required."},
            "preview_only": {"type": "boolean", "description": "Return plan preview without executing."},
            "preview_token": {"type": "string", "description": "Plan preview token required when preview acknowledgment is enforced."},
            "require_preview_ack": {"type": "boolean", "description": "If true, require preview_token before execution."},
        },
        "required": ["text"],
    },
    "home_assistant_todo": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "list, add, or remove"},
            "entity_id": {"type": "string", "description": "Todo entity id, for example todo.shopping"},
            "item": {"type": "string", "description": "Todo item text for add/remove actions"},
            "item_id": {"type": "string", "description": "Optional uid for remove actions"},
            "status": {"type": "string", "description": "Optional status filter for list actions"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["action", "entity_id"],
    },
    "home_assistant_timer": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "state, start, pause, cancel, or finish"},
            "entity_id": {"type": "string", "description": "Timer entity id, for example timer.kitchen"},
            "duration": {"type": "string", "description": "Optional duration when action=start (HH:MM:SS)."},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["action", "entity_id"],
    },
    "home_assistant_area_entities": {
        "type": "object",
        "properties": {
            "area": {"type": "string", "description": "Home Assistant area name."},
            "domain": {"type": "string", "description": "Optional entity domain filter (light, switch, climate, etc.)."},
            "include_states": {"type": "boolean", "description": "Include live entity states in response."},
        },
        "required": ["area"],
    },
    "media_control": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "media_player entity id"},
            "action": {"type": "string", "description": "play, pause, stop, volume_set, mute, unmute"},
            "volume": {"type": "number", "description": "Volume level between 0.0 and 1.0 for volume_set."},
            "dry_run": {"type": "boolean"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
            "preview_only": {"type": "boolean"},
            "preview_token": {"type": "string"},
            "require_preview_ack": {"type": "boolean"},
        },
        "required": ["entity_id", "action"],
    },
    "weather_lookup": {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "units": {"type": "string", "description": "metric or imperial"},
        },
        "required": ["location"],
    },
    "webhook_trigger": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "payload": {"type": "object"},
            "headers": {"type": "object"},
            "timeout_sec": {"type": "number"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
            "preview_only": {"type": "boolean"},
            "preview_token": {"type": "string"},
            "require_preview_ack": {"type": "boolean"},
        },
        "required": ["url"],
    },
    "webhook_inbound_list": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "webhook_inbound_clear": {
        "type": "object",
        "properties": {},
    },
    "slack_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["message"],
    },
    "discord_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["message"],
    },
    "email_send": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "confirm": {"type": "boolean"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
            "preview_only": {"type": "boolean"},
            "preview_token": {"type": "string"},
            "require_preview_ack": {"type": "boolean"},
        },
        "required": ["subject", "body"],
    },
    "email_summary": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "timer_create": {
        "type": "object",
        "properties": {
            "duration": {
                "description": "Duration in seconds (number) or string like '90s', '5m', '1h 15m'.",
            },
            "label": {"type": "string"},
        },
        "required": ["duration"],
    },
    "timer_list": {
        "type": "object",
        "properties": {
            "include_expired": {"type": "boolean"},
        },
    },
    "timer_cancel": {
        "type": "object",
        "properties": {
            "timer_id": {"type": "integer"},
            "label": {"type": "string"},
        },
    },
    "reminder_create": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "due": {
                "description": "Due timestamp as epoch seconds, ISO datetime, or relative duration like 'in 20m' / '45m'.",
            },
        },
        "required": ["text", "due"],
    },
    "reminder_list": {
        "type": "object",
        "properties": {
            "include_completed": {"type": "boolean"},
            "limit": {"type": "integer"},
        },
    },
    "reminder_complete": {
        "type": "object",
        "properties": {
            "reminder_id": {"type": "integer"},
        },
        "required": ["reminder_id"],
    },
    "reminder_notify_due": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "title": {"type": "string"},
            "nudge_policy": {"type": "string", "description": "interrupt, defer, or adaptive (optional override)."},
            "urgent_overdue_sec": {"type": "number", "description": "When nudge_policy=adaptive and quiet hours are active, overdue reminders beyond this threshold still send."},
        },
    },
    "calendar_events": {
        "type": "object",
        "properties": {
            "calendar_entity_id": {"type": "string"},
            "start": {"type": "string", "description": "Optional start datetime (ISO)."},
            "end": {"type": "string", "description": "Optional end datetime (ISO)."},
            "window_hours": {"type": "number", "description": "Window size when end is omitted."},
            "limit": {"type": "integer"},
        },
    },
    "calendar_next_event": {
        "type": "object",
        "properties": {
            "calendar_entity_id": {"type": "string"},
            "window_hours": {"type": "number"},
        },
    },
    "todoist_add_task": {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "description": {"type": "string"},
            "due_string": {"type": "string"},
            "priority": {"type": "integer"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["content"],
    },
    "todoist_list_tasks": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "format": {"type": "string", "description": "short (default) or verbose"},
        },
    },
    "pushover_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "title": {"type": "string"},
            "priority": {"type": "integer"},
        },
        "required": ["message"],
    },
    "get_time": {},
    "system_status": {},
    "system_status_contract": {},
    "jarvis_scorecard": {},
    "memory_add": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "description": "note, profile, summary, task, etc."},
            "scope": {
                "type": "string",
                "description": "Memory scope: preferences, people, projects, or household_rules.",
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "sensitivity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "source": {"type": "string"},
            "allow_pii": {"type": "boolean"},
        },
        "required": ["text"],
    },
    "memory_update": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer"},
            "text": {"type": "string"},
            "allow_pii": {"type": "boolean"},
        },
        "required": ["memory_id", "text"],
    },
    "memory_forget": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer"},
        },
        "required": ["memory_id"],
    },
    "memory_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "max_sensitivity": {"type": "number"},
            "include_sensitive": {"type": "boolean"},
            "hybrid_weight": {"type": "number"},
            "decay_enabled": {"type": "boolean"},
            "decay_half_life_days": {"type": "number"},
            "mmr_enabled": {"type": "boolean"},
            "mmr_lambda": {"type": "number"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "scopes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
    },
    "memory_status": {
        "type": "object",
        "properties": {
            "warm": {"type": "boolean"},
            "sync": {"type": "boolean"},
            "optimize": {"type": "boolean"},
            "vacuum": {"type": "boolean"},
        },
    },
    "memory_recent": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "kind": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "scopes": {"type": "array", "items": {"type": "string"}},
        },
    },
    "memory_summary_add": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["topic", "summary"],
    },
    "memory_summary_list": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "task_plan_create": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
    },
    "task_plan_list": {
        "type": "object",
        "properties": {
            "open_only": {"type": "boolean"},
        },
    },
    "task_plan_update": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
            "step_index": {"type": "integer", "description": "0-based index"},
            "status": {"type": "string", "description": "pending, in_progress, blocked, done"},
        },
        "required": ["plan_id", "step_index", "status"],
    },
    "task_plan_summary": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
        },
        "required": ["plan_id"],
    },
    "task_plan_next": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
        },
    },
    "tool_summary": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "tool_summary_text": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "skills_list": {
        "type": "object",
        "properties": {},
    },
    "skills_enable": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
    "skills_disable": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
    "skills_version": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
}

SERVICE_RUNTIME_REQUIRED_FIELDS: dict[str, set[str]] = {
    "smart_home": {"domain", "action", "entity_id"},
    "smart_home_state": {"entity_id"},
    "home_assistant_capabilities": {"entity_id"},
    "home_assistant_conversation": {"text"},
    "home_assistant_todo": {"action", "entity_id"},
    "home_assistant_timer": {"action", "entity_id"},
    "home_assistant_area_entities": {"area"},
    "media_control": {"entity_id", "action"},
    "weather_lookup": {"location"},
    "webhook_trigger": {"url"},
    "webhook_inbound_list": set(),
    "webhook_inbound_clear": set(),
    "slack_notify": {"message"},
    "discord_notify": {"message"},
    "email_send": {"subject", "body"},
    "email_summary": set(),
    "timer_create": {"duration"},
    "timer_list": set(),
    "timer_cancel": set(),
    "reminder_create": {"text", "due"},
    "reminder_list": set(),
    "reminder_complete": {"reminder_id"},
    "reminder_notify_due": set(),
    "calendar_events": set(),
    "calendar_next_event": set(),
    "todoist_add_task": {"content"},
    "todoist_list_tasks": set(),
    "pushover_notify": {"message"},
    "get_time": set(),
    "system_status": set(),
    "system_status_contract": set(),
    "jarvis_scorecard": set(),
    "memory_add": {"text"},
    "memory_update": {"memory_id", "text"},
    "memory_forget": {"memory_id"},
    "memory_search": {"query"},
    "memory_status": set(),
    "memory_recent": set(),
    "memory_summary_add": {"topic", "summary"},
    "memory_summary_list": set(),
    "task_plan_create": {"title", "steps"},
    "task_plan_list": set(),
    "task_plan_update": {"plan_id", "step_index", "status"},
    "task_plan_summary": {"plan_id"},
    "task_plan_next": set(),
    "tool_summary": set(),
    "tool_summary_text": set(),
    "skills_list": set(),
    "skills_enable": {"name"},
    "skills_disable": {"name"},
    "skills_version": {"name"},
}

# Backward compatibility for existing imports/tests.
SERVICE_ERROR_CODES = TOOL_SERVICE_ERROR_CODES


def _record_service_error(tool_name: str, start_time: float, code: str) -> None:
    normalized = normalize_service_error_code(code)
    integration = _integration_for_tool(tool_name)
    if integration is not None:
        _integration_record_failure(integration, normalized)
    record_summary(tool_name, "error", start_time, normalized)


def set_runtime_voice_state(state: dict[str, Any]) -> None:
    global _runtime_voice_state
    _runtime_voice_state = {str(key): value for key, value in state.items()} if isinstance(state, dict) else {}


def set_runtime_observability_state(state: dict[str, Any]) -> None:
    global _runtime_observability_state
    _runtime_observability_state = {str(key): value for key, value in state.items()} if isinstance(state, dict) else {}


def set_runtime_skills_state(state: dict[str, Any]) -> None:
    global _runtime_skills_state
    _runtime_skills_state = {str(key): value for key, value in state.items()} if isinstance(state, dict) else {}


def set_safe_mode(enabled: bool) -> None:
    global _safe_mode_enabled
    _safe_mode_enabled = bool(enabled)


def set_skill_registry(registry: SkillRegistry | None) -> None:
    global _skill_registry
    _skill_registry = registry


def bind(config: Config, memory_store: MemoryStore | None = None) -> None:
    global _config, _memory, _audit_log_max_bytes, _audit_log_backups
    global _home_permission_profile, _home_require_confirm_execute, _home_conversation_enabled
    global _home_conversation_permission_profile
    global _todoist_permission_profile, _notification_permission_profile, _email_permission_profile
    global _nudge_policy, _nudge_quiet_hours_start, _nudge_quiet_hours_end
    global _todoist_timeout_sec, _pushover_timeout_sec
    global _email_smtp_host, _email_smtp_port, _email_smtp_username, _email_smtp_password
    global _email_from, _email_default_to, _email_use_tls, _email_timeout_sec
    global _weather_units, _weather_timeout_sec
    global _webhook_allowlist, _webhook_auth_token, _webhook_timeout_sec
    global _turn_timeout_listen_sec, _turn_timeout_think_sec, _turn_timeout_speak_sec, _turn_timeout_act_sec
    global _slack_webhook_url, _discord_webhook_url
    global _identity_enforcement_enabled, _identity_default_user, _identity_default_profile
    global _identity_user_profiles, _identity_trusted_users, _identity_require_approval, _identity_approval_code
    global _plan_preview_require_ack, _safe_mode_enabled
    global _memory_retention_days, _audit_retention_days
    global _memory_pii_guardrails_enabled, _audit_encryption_enabled, _data_encryption_key
    global _timer_id_seq, _reminder_id_seq, _integration_circuit_breakers, _recovery_journal_path
    _config = config
    _memory = memory_store
    _audit_log_max_bytes = int(config.audit_log_max_bytes)
    _audit_log_backups = int(config.audit_log_backups)
    _home_permission_profile = str(getattr(config, "home_permission_profile", "control")).strip().lower()
    if _home_permission_profile not in {"readonly", "control"}:
        _home_permission_profile = "control"
    _home_require_confirm_execute = bool(getattr(config, "home_require_confirm_execute", False))
    _home_conversation_enabled = bool(getattr(config, "home_conversation_enabled", False))
    _home_conversation_permission_profile = str(
        getattr(config, "home_conversation_permission_profile", "readonly")
    ).strip().lower()
    if _home_conversation_permission_profile not in {"readonly", "control"}:
        _home_conversation_permission_profile = "readonly"
    _todoist_permission_profile = str(getattr(config, "todoist_permission_profile", "control")).strip().lower()
    if _todoist_permission_profile not in {"readonly", "control"}:
        _todoist_permission_profile = "control"
    _notification_permission_profile = str(
        getattr(config, "notification_permission_profile", "allow")
    ).strip().lower()
    if _notification_permission_profile not in {"off", "allow"}:
        _notification_permission_profile = "allow"
    _nudge_policy = str(getattr(config, "nudge_policy", "adaptive")).strip().lower()
    if _nudge_policy not in {"interrupt", "defer", "adaptive"}:
        _nudge_policy = "adaptive"
    _nudge_quiet_hours_start = str(getattr(config, "nudge_quiet_hours_start", "22:00")).strip()
    _nudge_quiet_hours_end = str(getattr(config, "nudge_quiet_hours_end", "07:00")).strip()
    _email_permission_profile = str(getattr(config, "email_permission_profile", "readonly")).strip().lower()
    if _email_permission_profile not in {"readonly", "control"}:
        _email_permission_profile = "readonly"
    _todoist_timeout_sec = float(getattr(config, "todoist_timeout_sec", 10.0))
    _pushover_timeout_sec = float(getattr(config, "pushover_timeout_sec", 10.0))
    _email_smtp_host = str(getattr(config, "email_smtp_host", "")).strip()
    _email_smtp_port = int(getattr(config, "email_smtp_port", 587))
    _email_smtp_username = str(getattr(config, "email_smtp_username", "")).strip()
    _email_smtp_password = str(getattr(config, "email_smtp_password", "")).strip()
    _email_from = str(getattr(config, "email_from", "")).strip()
    _email_default_to = str(getattr(config, "email_default_to", "")).strip()
    _email_use_tls = bool(getattr(config, "email_use_tls", True))
    _email_timeout_sec = float(getattr(config, "email_timeout_sec", 10.0))
    _weather_units = str(getattr(config, "weather_units", "metric")).strip().lower()
    if _weather_units not in {"metric", "imperial"}:
        _weather_units = "metric"
    _weather_timeout_sec = float(getattr(config, "weather_timeout_sec", 8.0))
    _webhook_allowlist = [str(host).strip().lower() for host in getattr(config, "webhook_allowlist", []) if str(host).strip()]
    _webhook_auth_token = str(getattr(config, "webhook_auth_token", "")).strip()
    _webhook_timeout_sec = float(getattr(config, "webhook_timeout_sec", 8.0))
    _turn_timeout_listen_sec = float(getattr(config, "watchdog_listening_timeout_sec", 30.0))
    _turn_timeout_think_sec = float(getattr(config, "watchdog_thinking_timeout_sec", 60.0))
    _turn_timeout_speak_sec = float(getattr(config, "watchdog_speaking_timeout_sec", 45.0))
    _turn_timeout_act_sec = float(getattr(config, "turn_timeout_act_sec", 30.0))
    _slack_webhook_url = str(getattr(config, "slack_webhook_url", "")).strip()
    _discord_webhook_url = str(getattr(config, "discord_webhook_url", "")).strip()
    _identity_enforcement_enabled = bool(getattr(config, "identity_enforcement_enabled", False))
    _identity_default_user = str(getattr(config, "identity_default_user", "owner")).strip().lower() or "owner"
    _identity_default_profile = str(getattr(config, "identity_default_profile", "control")).strip().lower()
    if _identity_default_profile not in {"deny", "readonly", "control", "trusted"}:
        _identity_default_profile = "control"
    raw_profiles = getattr(config, "identity_user_profiles", {}) or {}
    if isinstance(raw_profiles, dict):
        _identity_user_profiles = {
            str(user).strip().lower(): str(profile).strip().lower()
            for user, profile in raw_profiles.items()
            if str(user).strip()
            and str(profile).strip().lower() in {"deny", "readonly", "control", "trusted"}
        }
    else:
        _identity_user_profiles = {}
    raw_trusted_users = getattr(config, "identity_trusted_users", []) or []
    _identity_trusted_users = {
        str(user).strip().lower() for user in raw_trusted_users if str(user).strip()
    }
    _identity_require_approval = bool(getattr(config, "identity_require_approval", True))
    _identity_approval_code = str(getattr(config, "identity_approval_code", "")).strip()
    _plan_preview_require_ack = bool(getattr(config, "plan_preview_require_ack", False))
    _safe_mode_enabled = bool(getattr(config, "safe_mode_enabled", False))
    _memory_retention_days = max(0.0, float(getattr(config, "memory_retention_days", 0.0)))
    _audit_retention_days = max(0.0, float(getattr(config, "audit_retention_days", 0.0)))
    _memory_pii_guardrails_enabled = bool(getattr(config, "memory_pii_guardrails_enabled", True))
    _audit_encryption_enabled = bool(getattr(config, "audit_encryption_enabled", False))
    _data_encryption_key = str(getattr(config, "data_encryption_key", "")).strip()
    _recovery_journal_path = Path(
        str(getattr(config, "recovery_journal_path", str(DEFAULT_RECOVERY_JOURNAL)))
    ).expanduser()
    _configure_audit_encryption(enabled=_audit_encryption_enabled, key=_data_encryption_key)
    _action_last_seen.clear()
    _ha_state_cache.clear()
    _timers.clear()
    _timer_id_seq = 1
    _reminders.clear()
    _reminder_id_seq = 1
    _email_history.clear()
    _pending_plan_previews.clear()
    _runtime_voice_state.clear()
    _runtime_observability_state.clear()
    _runtime_skills_state.clear()
    _integration_circuit_breakers.clear()
    for integration in sorted(set(INTEGRATION_TOOL_MAP.values())):
        _ensure_circuit_breaker_state(integration)
    _recovery_reconcile_interrupted()
    _load_timers_from_store()
    _load_reminders_from_store()
    global _tool_allowlist, _tool_denylist
    _tool_allowlist = list(config.tool_allowlist)
    _tool_denylist = list(config.tool_denylist)
    # Ensure audit dir exists
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    _apply_retention_policies()


def _tool_permitted(name: str) -> bool:
    if _safe_mode_enabled and name in SAFE_MODE_BLOCKED_TOOLS:
        return False
    if _home_permission_profile == "readonly" and name in {"smart_home", "media_control"}:
        return False
    if _todoist_permission_profile == "readonly" and name == "todoist_add_task":
        return False
    if _email_permission_profile == "readonly" and name == "email_send":
        return False
    if _notification_permission_profile == "off" and name in {"pushover_notify", "slack_notify", "discord_notify"}:
        return False
    if (
        name.startswith("skills_")
        and name != "skills_list"
        and _skill_registry is not None
        and not _skill_registry.enabled
    ):
        return False
    if _config is not None and not _config.home_enabled:
        if name in {
            "smart_home",
            "smart_home_state",
            "home_assistant_capabilities",
            "home_assistant_conversation",
            "home_assistant_todo",
            "home_assistant_timer",
            "home_assistant_area_entities",
            "media_control",
            "calendar_events",
            "calendar_next_event",
        }:
            return False
    return is_tool_allowed(name, _tool_allowlist, _tool_denylist)


def _configure_audit_encryption(*, enabled: bool, key: str) -> None:
    global _audit_encryption_enabled, _data_encryption_key, _audit_fernet
    _audit_encryption_enabled = bool(enabled)
    _data_encryption_key = str(key or "").strip()
    if not _audit_encryption_enabled:
        _audit_fernet = None
        return
    if not _data_encryption_key or Fernet is None:
        _audit_fernet = None
        return
    candidate = _data_encryption_key.encode("utf-8")
    try:
        Fernet(candidate)
        fernet_key = candidate
    except Exception:
        digest = hashlib.sha256(candidate).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
    _audit_fernet = Fernet(fernet_key)


def _encrypt_audit_line(payload: dict[str, Any]) -> str:
    line = json.dumps(payload, default=str)
    if not _audit_encryption_enabled or _audit_fernet is None:
        return line
    token = _audit_fernet.encrypt(line.encode("utf-8")).decode("utf-8")
    return json.dumps({"enc": token}, default=str)


def _decode_audit_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if isinstance(payload, dict) and "enc" in payload:
        token = str(payload.get("enc", "")).strip()
        if not token or _audit_fernet is None:
            return {"encrypted": True, "error": "missing_encryption_key"}
        try:
            raw = _audit_fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return {"encrypted": True, "error": "invalid_token"}
        try:
            decrypted = json.loads(raw)
        except Exception:
            return {"encrypted": True, "error": "invalid_payload"}
        if isinstance(decrypted, dict):
            return decrypted
        return {"encrypted": True, "error": "invalid_payload"}
    return payload if isinstance(payload, dict) else None


def decode_audit_entry_line(line: str) -> dict[str, Any] | None:
    return _decode_audit_line(line)


def _audit_outcome(details: dict[str, Any]) -> str:
    policy_decision = str(details.get("policy_decision", "")).strip().lower()
    result = str(details.get("result", "")).strip().lower()
    if policy_decision in {"denied", "blocked"}:
        return "blocked"
    if policy_decision in {"allowed", "execute"}:
        return "allowed"
    if policy_decision == "dry_run":
        return "dry_run"
    if policy_decision == "preview_required":
        return "preview_required"
    if result in {"denied", "blocked"}:
        return "blocked"
    if result in {"ok", "success", "delivered"}:
        return "allowed"
    if result in {"timeout", "cancelled", "network_client_error", "http_error", "api_error", "auth", "unexpected"}:
        return "failed"
    if result in {"missing_config", "missing_fields", "invalid_data", "invalid_json"}:
        return "failed"
    if result:
        return "observed"
    return "unknown"


def _audit_reason_code(details: dict[str, Any]) -> str:
    reason = str(details.get("reason", "")).strip().lower()
    if reason:
        return reason
    policy_decision = str(details.get("policy_decision", "")).strip().lower()
    if policy_decision:
        return policy_decision
    result = str(details.get("result", "")).strip().lower()
    return result


def _humanize_chain_token(token: str) -> str:
    text = str(token).strip()
    if not text:
        return ""
    if text.startswith("deny:"):
        reason = text.split(":", 1)[1].replace("_", " ")
        return f"deny ({reason})"
    if text.startswith("decision:"):
        reason = text.split(":", 1)[1].replace("_", " ")
        return f"decision ({reason})"
    if text.startswith("tool="):
        return f"tool {text.split('=', 1)[1]}"
    if text.startswith("requester="):
        return f"requester {text.split('=', 1)[1]}"
    if text.startswith("profile="):
        return f"profile {text.split('=', 1)[1]}"
    return text.replace("_", " ")


def _audit_decision_explanation(action: str, details: dict[str, Any]) -> str:
    outcome = _audit_outcome(details)
    reason_code = _audit_reason_code(details)
    if outcome == "blocked":
        intro = "Blocked"
    elif outcome == "allowed":
        intro = "Allowed"
    elif outcome == "dry_run":
        intro = "Dry run"
    elif outcome == "preview_required":
        intro = "Preview required"
    elif outcome == "failed":
        intro = "Failed"
    elif outcome == "observed":
        intro = "Recorded"
    else:
        intro = "Logged"

    reason_msg = AUDIT_REASON_MESSAGES.get(reason_code, "")
    if not reason_msg and reason_code:
        reason_msg = reason_code.replace("_", " ")

    chain = details.get("decision_chain")
    chain_tokens = chain if isinstance(chain, list) else []
    chain_hint = ""
    if chain_tokens:
        tail = [_humanize_chain_token(item) for item in chain_tokens[-2:]]
        tail = [item for item in tail if item]
        if tail:
            chain_hint = f" Decision path: {' -> '.join(tail)}."

    action_label = str(action).replace("_", " ").strip() or "action"
    if reason_msg:
        return f"{intro}: {action_label} was {reason_msg}.{chain_hint}".strip()
    return f"{intro}: {action_label} was processed.{chain_hint}".strip()


def _audit(action: str, details: dict) -> None:
    """Append to local audit log: what was heard, what was done, why."""
    enriched = {str(key): value for key, value in details.items()}
    if "requester_id" not in enriched:
        enriched["requester_id"] = _identity_default_user
    if "requester_profile" not in enriched:
        enriched["requester_profile"] = _identity_user_profiles.get(
            str(enriched["requester_id"]).strip().lower(),
            _identity_default_profile,
        )
    if "requester_trusted" not in enriched:
        requester = str(enriched["requester_id"]).strip().lower()
        enriched["requester_trusted"] = requester in _identity_trusted_users or str(
            enriched["requester_profile"]
        ).strip().lower() == "trusted"
    if "speaker_verified" not in enriched:
        enriched["speaker_verified"] = False
    if "identity_source" not in enriched:
        enriched["identity_source"] = "default"
    if "decision_chain" not in enriched:
        enriched["decision_chain"] = ["identity_default_context"]
    if "decision_outcome" not in enriched:
        enriched["decision_outcome"] = _audit_outcome(enriched)
    if "decision_reason" not in enriched:
        enriched["decision_reason"] = _audit_reason_code(enriched)
    if "decision_explanation" not in enriched:
        enriched["decision_explanation"] = _audit_decision_explanation(action, enriched)

    metadata_only = _metadata_only_audit_details(action, enriched)
    redacted = _redact_sensitive_for_audit(metadata_only)
    details_json = json.dumps(redacted, default=str)
    entry = {
        "timestamp": time.time(),
        "action": action,
        **redacted,
    }
    try:
        _rotate_audit_log_if_needed()
        with open(AUDIT_LOG, "a") as f:
            f.write(_encrypt_audit_line(entry) + "\n")
    except OSError as e:
        log.warning("Failed to write audit log: %s", e)
    log.info("AUDIT: %s — %s", action, details_json)


def _rotate_audit_log_if_needed() -> None:
    if _audit_log_backups < 1:
        return
    try:
        if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size >= _audit_log_max_bytes:
            for idx in range(_audit_log_backups, 0, -1):
                src = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx}")
                dst = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx + 1}")
                if src.exists():
                    if idx == _audit_log_backups:
                        src.unlink(missing_ok=True)
                    else:
                        src.rename(dst)
            rotated = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.1")
            AUDIT_LOG.rename(rotated)
    except OSError as e:
        log.warning("Failed to rotate audit log: %s", e)


def _redact_sensitive_for_audit(value: Any, *, key_hint: str | None = None) -> Any:
    if key_hint:
        lowered = key_hint.strip().lower()
        if any(token in lowered for token in SENSITIVE_AUDIT_KEY_TOKENS):
            return AUDIT_REDACTED
    if isinstance(value, dict):
        return {
            str(key): _redact_sensitive_for_audit(item, key_hint=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_for_audit(item, key_hint=key_hint) for item in value]
    return value


def _metadata_only_audit_details(action: str, details: dict[str, Any]) -> dict[str, Any]:
    forbidden = AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS.get(action)
    if not forbidden:
        return {str(key): value for key, value in details.items()}
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        key_text = str(key)
        if key_text.strip().lower() in forbidden:
            continue
        sanitized[key_text] = value
    return sanitized


def _sanitize_inbound_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in (headers or {}).items():
        key_text = str(key)
        lowered = key_text.strip().lower()
        value_text = str(value)
        if any(token in lowered for token in INBOUND_REDACT_HEADER_TOKENS):
            sanitized[key_text] = AUDIT_REDACTED
            continue
        sanitized[key_text] = value_text
    return sanitized


def _sanitize_inbound_payload(value: Any, *, key_hint: str | None = None, depth: int = 0) -> Any:
    if depth > 8:
        return "<max_depth>"
    if key_hint:
        lowered = key_hint.strip().lower()
        if any(token in lowered for token in SENSITIVE_AUDIT_KEY_TOKENS):
            return AUDIT_REDACTED
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= INBOUND_MAX_COLLECTION_ITEMS:
                out["<truncated_keys>"] = max(0, len(value) - INBOUND_MAX_COLLECTION_ITEMS)
                break
            key_text = str(key)
            out[key_text] = _sanitize_inbound_payload(item, key_hint=key_text, depth=depth + 1)
        return out
    if isinstance(value, list):
        limited = value[:INBOUND_MAX_COLLECTION_ITEMS]
        out = [_sanitize_inbound_payload(item, key_hint=key_hint, depth=depth + 1) for item in limited]
        if len(value) > INBOUND_MAX_COLLECTION_ITEMS:
            out.append(f"<truncated_items:{len(value) - INBOUND_MAX_COLLECTION_ITEMS}>")
        return out
    if isinstance(value, str):
        if len(value) > INBOUND_MAX_STRING_CHARS:
            return value[:INBOUND_MAX_STRING_CHARS] + "...<truncated>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    if len(text) > INBOUND_MAX_STRING_CHARS:
        return text[:INBOUND_MAX_STRING_CHARS] + "...<truncated>"
    return text


def _contains_pii(text: str) -> bool:
    sample = text.strip()
    if not sample:
        return False
    return any(pattern.search(sample) is not None for pattern in _PII_PATTERNS)


def _identity_context(args: dict[str, Any] | None) -> dict[str, Any]:
    payload = args if isinstance(args, dict) else {}
    request_context = payload.get("request_context")
    context_payload = request_context if isinstance(request_context, dict) else {}

    requester_id = str(payload.get("requester_id", "")).strip().lower()
    source = "requester_id"
    if not requester_id:
        requester_id = str(context_payload.get("requester_id") or context_payload.get("user_id") or "").strip().lower()
        source = "request_context" if requester_id else "default"
    if not requester_id:
        requester_id = _identity_default_user
    profile = _identity_user_profiles.get(requester_id, _identity_default_profile)
    if profile not in {"deny", "readonly", "control", "trusted"}:
        profile = "control"
    speaker_verified = _as_bool(
        payload.get("speaker_verified", context_payload.get("speaker_verified")),
        default=False,
    )
    trusted = requester_id in _identity_trusted_users or profile == "trusted" or speaker_verified
    return {
        "requester_id": requester_id,
        "profile": profile,
        "trusted": trusted,
        "speaker_verified": speaker_verified,
        "source": source,
    }


def _identity_audit_fields(context: dict[str, Any], decision_chain: list[str] | None = None) -> dict[str, Any]:
    chain = [str(item) for item in (decision_chain or []) if str(item).strip()]
    if not chain:
        chain = ["identity_context_applied"]
    return {
        "requester_id": str(context.get("requester_id", "")),
        "requester_profile": str(context.get("profile", "control")),
        "requester_trusted": bool(context.get("trusted", False)),
        "speaker_verified": bool(context.get("speaker_verified", False)),
        "identity_source": str(context.get("source", "default")),
        "decision_chain": chain,
    }


def _identity_authorize(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    mutating: bool,
    high_risk: bool,
) -> tuple[bool, str | None, dict[str, Any], list[str]]:
    context = _identity_context(args)
    chain = [
        f"tool={tool_name}",
        f"requester={context['requester_id']}",
        f"profile={context['profile']}",
    ]
    if _safe_mode_enabled and mutating:
        chain.append("deny:safe_mode")
        return (
            False,
            "Safe mode is enabled. Mutating actions are blocked; disable safe mode or use dry-run where supported.",
            context,
            chain,
        )
    if not _identity_enforcement_enabled:
        chain.append("identity_enforcement_disabled")
        return True, None, context, chain

    profile = str(context.get("profile", "control"))
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
    if high_risk and _identity_require_approval:
        payload = args if isinstance(args, dict) else {}
        approved = _as_bool(payload.get("approved"), default=False)
        approval_code = str(payload.get("approval_code", "")).strip()
        code_valid = bool(_identity_approval_code) and bool(approval_code) and hmac.compare_digest(
            approval_code,
            _identity_approval_code,
        )
        trusted_approved = bool(context.get("trusted", False)) and approved
        if not (code_valid or trusted_approved):
            chain.append("deny:approval_required")
            if _identity_approval_code:
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


def _identity_enriched_audit(details: dict[str, Any], identity: dict[str, Any], decision_chain: list[str]) -> dict[str, Any]:
    return {**details, **_identity_audit_fields(identity, decision_chain)}


def _tokenized_words(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_']+", text.lower()) if token]


def _is_ambiguous_high_risk_text(text: str) -> bool:
    sample = str(text).strip().lower()
    if not sample:
        return False
    words = _tokenized_words(sample)
    if not words:
        return False
    has_risk_term = any(term in sample for term in HIGH_RISK_INTENT_TERMS)
    if not has_risk_term:
        return False
    has_ambiguous_reference = any(token in AMBIGUOUS_REFERENCE_TERMS for token in words)
    has_explicit_target = any(token in EXPLICIT_TARGET_TERMS for token in words)
    return has_ambiguous_reference and not has_explicit_target


def _is_ambiguous_entity_target(entity_id: str) -> bool:
    clean = str(entity_id or "").strip().lower()
    if "." not in clean:
        return False
    name = clean.split(".", 1)[1]
    words = _tokenized_words(name.replace("-", "_"))
    if not words:
        return False
    return any(token in {"all", "group", "everything", "everyone"} for token in words)


def _plan_preview_signature(tool_name: str, payload: dict[str, Any]) -> str:
    normalized = {"tool": tool_name, "payload": payload}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _prune_plan_previews(now_ts: float | None = None) -> None:
    if not _pending_plan_previews:
        return
    current = time.time() if now_ts is None else float(now_ts)
    stale = [token for token, item in _pending_plan_previews.items() if float(item.get("expires_at", 0.0)) <= current]
    for token in stale:
        _pending_plan_previews.pop(token, None)
    if len(_pending_plan_previews) <= PLAN_PREVIEW_MAX_PENDING:
        return
    overflow = len(_pending_plan_previews) - PLAN_PREVIEW_MAX_PENDING
    oldest = sorted(
        _pending_plan_previews.items(),
        key=lambda pair: float(pair[1].get("issued_at", 0.0)),
    )[:overflow]
    for token, _ in oldest:
        _pending_plan_previews.pop(token, None)


def _issue_plan_preview_token(tool_name: str, signature: str, risk: str, summary: str) -> str:
    now = time.time()
    token = secrets.token_urlsafe(12)
    _pending_plan_previews[token] = {
        "tool": tool_name,
        "signature": signature,
        "risk": risk,
        "summary": summary,
        "issued_at": now,
        "expires_at": now + PLAN_PREVIEW_TTL_SEC,
    }
    _prune_plan_previews(now)
    return token


def _consume_plan_preview_token(token: str, *, tool_name: str, signature: str) -> bool:
    if not token:
        return False
    _prune_plan_previews()
    row = _pending_plan_previews.get(token)
    if not isinstance(row, dict):
        return False
    if str(row.get("tool", "")) != tool_name:
        return False
    if str(row.get("signature", "")) != signature:
        return False
    _pending_plan_previews.pop(token, None)
    return True


def _plan_preview_message(*, summary: str, risk: str, token: str, ttl_sec: float = PLAN_PREVIEW_TTL_SEC) -> str:
    ttl = max(1, int(round(ttl_sec)))
    return (
        f"PLAN PREVIEW ({risk} risk): {summary}. "
        f"To execute, resend with preview_token={token} within {ttl}s."
    )


def _preview_gate(
    *,
    tool_name: str,
    args: dict[str, Any],
    risk: str,
    summary: str,
    signature_payload: dict[str, Any],
    enforce_default: bool,
) -> str | None:
    enforce = _as_bool(args.get("require_preview_ack"), default=enforce_default)
    preview_only = _as_bool(args.get("preview_only"), default=False) or _as_bool(args.get("preview"), default=False)
    preview_token = str(args.get("preview_token", "")).strip()
    signature = _plan_preview_signature(tool_name, signature_payload)

    if preview_only:
        issued = _issue_plan_preview_token(tool_name, signature, risk, summary)
        return _plan_preview_message(summary=summary, risk=risk, token=issued)
    if not enforce:
        return None
    if not preview_token:
        issued = _issue_plan_preview_token(tool_name, signature, risk, summary)
        return _plan_preview_message(summary=summary, risk=risk, token=issued)
    if not _consume_plan_preview_token(preview_token, tool_name=tool_name, signature=signature):
        return "Invalid or expired preview_token. Request a new plan preview with preview_only=true."
    return None


def _format_tool_summaries(items: list[dict[str, object]]) -> str:
    if not items:
        return "No recent tool activity."
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "tool"))
        status = str(item.get("status", "unknown"))
        try:
            duration = float(item.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        if not math.isfinite(duration):
            duration = 0.0
        detail = item.get("detail")
        effect = item.get("effect")
        risk = item.get("risk")
        detail_text = f" ({detail})" if detail else ""
        effect_text = f" effect={effect}" if effect else ""
        risk_text = f" risk={risk}" if risk else ""
        lines.append(f"- {name}: {status} ({duration:.0f}ms){detail_text}{effect_text}{risk_text}")
    if not lines:
        return "No recent tool activity."
    return "\n".join(lines)


def _now_local() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return default
        return bool(value)
    return default


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        parsed = default
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            parsed = default
        else:
            parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if text and (text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit())):
            try:
                parsed = int(text)
            except ValueError:
                parsed = default
        else:
            parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_exact_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit()):
            try:
                return int(text)
            except ValueError:
                return None
        return None
    return None


def _as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        parsed = default
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
    if not math.isfinite(parsed):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _effective_act_timeout(total_sec: Any, *, minimum: float = 0.1, maximum: float = 120.0) -> float:
    requested = _as_float(total_sec, _turn_timeout_act_sec, minimum=minimum, maximum=maximum)
    budget = _as_float(_turn_timeout_act_sec, requested, minimum=minimum, maximum=maximum)
    return min(requested, budget)


def _integration_for_tool(tool_name: str) -> str | None:
    return INTEGRATION_TOOL_MAP.get(str(tool_name).strip().lower())


def _ensure_circuit_breaker_state(integration: str) -> dict[str, Any]:
    normalized = str(integration or "").strip().lower()
    if not normalized:
        normalized = "unknown"
    state = _integration_circuit_breakers.get(normalized)
    if state is not None:
        return state
    state = {
        "integration": normalized,
        "consecutive_failures": 0,
        "open_until": 0.0,
        "opened_count": 0,
        "cooldown_sec": 0.0,
        "last_error": "",
        "last_failure_at": 0.0,
        "last_success_at": 0.0,
    }
    _integration_circuit_breakers[normalized] = state
    return state


def _integration_circuit_open(integration: str, *, now_ts: float | None = None) -> tuple[bool, float]:
    state = _ensure_circuit_breaker_state(integration)
    now = time.time() if now_ts is None else float(now_ts)
    open_until = float(state.get("open_until", 0.0) or 0.0)
    if open_until <= now:
        return False, 0.0
    return True, max(0.0, open_until - now)


def _integration_record_failure(integration: str, error_code: str) -> None:
    normalized_code = str(error_code or "").strip().lower()
    if normalized_code not in CIRCUIT_BREAKER_ERROR_CODES:
        return
    state = _ensure_circuit_breaker_state(integration)
    now = time.time()
    failures = int(state.get("consecutive_failures", 0)) + 1
    state["consecutive_failures"] = failures
    state["last_error"] = normalized_code
    state["last_failure_at"] = now
    if failures < CIRCUIT_BREAKER_FAILURE_THRESHOLD:
        return
    opened_count = int(state.get("opened_count", 0))
    cooldown = min(
        CIRCUIT_BREAKER_MAX_COOLDOWN_SEC,
        CIRCUIT_BREAKER_BASE_COOLDOWN_SEC * (2 ** max(0, opened_count)),
    )
    state["cooldown_sec"] = float(cooldown)
    state["open_until"] = now + float(cooldown)
    state["opened_count"] = opened_count + 1


def _integration_record_success(integration: str) -> None:
    state = _ensure_circuit_breaker_state(integration)
    state["consecutive_failures"] = 0
    state["open_until"] = 0.0
    state["cooldown_sec"] = 0.0
    state["last_error"] = ""
    state["last_success_at"] = time.time()


def _integration_circuit_snapshot(integration: str, *, now_ts: float | None = None) -> dict[str, Any]:
    state = _ensure_circuit_breaker_state(integration)
    now = time.time() if now_ts is None else float(now_ts)
    open_until = float(state.get("open_until", 0.0) or 0.0)
    return {
        "open": open_until > now,
        "open_remaining_sec": max(0.0, open_until - now),
        "consecutive_failures": int(state.get("consecutive_failures", 0)),
        "opened_count": int(state.get("opened_count", 0)),
        "cooldown_sec": float(state.get("cooldown_sec", 0.0) or 0.0),
        "last_error": str(state.get("last_error", "")),
        "last_failure_at": float(state.get("last_failure_at", 0.0) or 0.0),
        "last_success_at": float(state.get("last_success_at", 0.0) or 0.0),
    }


def _integration_circuit_open_message(integration: str, remaining_sec: float) -> str:
    label = str(integration).replace("_", " ").strip() or "integration"
    return f"{label.title()} circuit breaker is open; retry in about {int(max(1.0, remaining_sec))}s."


def _normalize_nudge_policy(value: Any) -> str:
    normalized = str(value or "adaptive").strip().lower()
    if normalized in {"interrupt", "defer", "adaptive"}:
        return normalized
    return "adaptive"


def _hhmm_to_minutes(value: str) -> int | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    return (hours * 60) + minutes


def _quiet_window_active(*, now_ts: float | None = None) -> bool:
    start = _hhmm_to_minutes(_nudge_quiet_hours_start)
    end = _hhmm_to_minutes(_nudge_quiet_hours_end)
    if start is None or end is None or start == end:
        return False
    local = time.localtime(time.time() if now_ts is None else float(now_ts))
    minute = (local.tm_hour * 60) + local.tm_min
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def _duration_seconds(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0.0:
            return None
        return min(seconds, TIMER_MAX_SECONDS)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    try:
        parsed = float(text)
        if math.isfinite(parsed) and parsed > 0.0:
            return min(parsed, TIMER_MAX_SECONDS)
    except ValueError:
        pass
    total = 0.0
    cursor = 0
    for match in _DURATION_SEGMENT_RE.finditer(text):
        if match.start() != cursor and text[cursor:match.start()].strip():
            return None
        value_part = float(match.group("value"))
        unit = match.group("unit").lower()
        if unit.startswith("h"):
            total += value_part * 3600.0
        elif unit.startswith("m"):
            total += value_part * 60.0
        else:
            total += value_part
        cursor = match.end()
    if cursor != len(text) and text[cursor:].strip():
        return None
    if total <= 0.0:
        return None
    return min(total, TIMER_MAX_SECONDS)


def _local_timezone():
    tz = datetime.now().astimezone().tzinfo
    return tz if tz is not None else timezone.utc


def _parse_datetime_text(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_local_timezone())
    return parsed


def _parse_due_timestamp(value: Any, *, now_ts: float | None = None) -> float | None:
    now = time.time() if now_ts is None else float(now_ts)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidate = float(value)
        if not math.isfinite(candidate) or candidate <= 0.0:
            return None
        if candidate >= 1_000_000_000.0:
            return candidate
        return now + min(candidate, TIMER_MAX_SECONDS)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    numeric = None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and math.isfinite(numeric) and numeric > 0.0:
        if numeric >= 1_000_000_000.0:
            return numeric
        return now + min(numeric, TIMER_MAX_SECONDS)
    if lowered.startswith("in "):
        relative = _duration_seconds(lowered[3:])
        if relative is not None:
            return now + relative
    relative = _duration_seconds(text)
    if relative is not None:
        return now + relative
    parsed = _parse_datetime_text(text)
    if parsed is None:
        return None
    return parsed.timestamp()


def _timestamp_to_iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _format_duration(seconds: float) -> str:
    remaining = max(0, int(round(seconds)))
    hours, rem = divmod(remaining, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _allocate_timer_id() -> int:
    global _timer_id_seq
    timer_id = _timer_id_seq
    _timer_id_seq += 1
    return timer_id


def _allocate_reminder_id() -> int:
    global _reminder_id_seq
    reminder_id = _reminder_id_seq
    _reminder_id_seq += 1
    return reminder_id


def _retry_backoff_delay(
    attempt_index: int,
    *,
    base_delay_sec: float = RETRY_BASE_DELAY_SEC,
    max_delay_sec: float = RETRY_MAX_DELAY_SEC,
    jitter_ratio: float = RETRY_JITTER_RATIO,
    jitter_sample: float | None = None,
) -> float:
    step = max(0, int(attempt_index))
    base_delay = min(max_delay_sec, base_delay_sec * (2 ** step))
    sample = random.random() if jitter_sample is None else float(jitter_sample)
    sample = min(1.0, max(0.0, sample))
    jitter = base_delay * jitter_ratio * ((sample * 2.0) - 1.0)
    return max(0.0, base_delay + jitter)


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or None
    text = str(value).strip()
    return [text] if text else None


def _action_key(domain: str, action: str, entity_id: str) -> str:
    return f"{domain}:{action}:{entity_id}"


def _prune_action_history(now: float | None = None) -> None:
    if not _action_last_seen:
        return
    current = time.monotonic() if now is None else now
    cutoff = current - ACTION_HISTORY_RETENTION_SEC
    stale_keys = [key for key, ts in _action_last_seen.items() if ts < cutoff]
    for key in stale_keys:
        _action_last_seen.pop(key, None)
    if len(_action_last_seen) <= ACTION_HISTORY_MAX_ENTRIES:
        return
    over = len(_action_last_seen) - ACTION_HISTORY_MAX_ENTRIES
    oldest = sorted(_action_last_seen.items(), key=lambda item: item[1])[:over]
    for key, _ in oldest:
        _action_last_seen.pop(key, None)


def _cooldown_active(domain: str, action: str, entity_id: str) -> bool:
    now = time.monotonic()
    _prune_action_history(now)
    key = _action_key(domain, action, entity_id)
    last = _action_last_seen.get(key)
    if last is None:
        return False
    return (now - last) < ACTION_COOLDOWN_SEC


def _touch_action(domain: str, action: str, entity_id: str) -> None:
    now = time.monotonic()
    _action_last_seen[_action_key(domain, action, entity_id)] = now
    _prune_action_history(now)


def _audit_status() -> dict[str, Any]:
    try:
        exists = AUDIT_LOG.exists()
        size_bytes = AUDIT_LOG.stat().st_size if exists else 0
    except OSError:
        exists = False
        size_bytes = 0
    backups = []
    for idx in range(1, _audit_log_backups + 1):
        backup_path = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx}")
        try:
            if backup_path.exists():
                backups.append(
                    {
                        "path": str(backup_path),
                        "size_bytes": int(backup_path.stat().st_size),
                    }
                )
        except OSError:
            continue
    return {
        "path": str(AUDIT_LOG),
        "exists": exists,
        "size_bytes": int(size_bytes),
        "max_bytes": int(_audit_log_max_bytes),
        "encrypted": bool(_audit_encryption_enabled and _audit_fernet is not None),
        "encryption_configured": bool(_audit_encryption_enabled),
        "backups": backups,
        "redaction_enabled": bool(SENSITIVE_AUDIT_KEY_TOKENS),
        "redaction_key_count": len(SENSITIVE_AUDIT_KEY_TOKENS),
        "metadata_only_actions": sorted(AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS),
    }


def _read_recovery_journal_entries() -> list[dict[str, Any]]:
    path = _recovery_journal_path
    if not path.exists():
        return []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _write_recovery_journal_entry(payload: dict[str, Any]) -> None:
    path = _recovery_journal_path
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, default=str)
    try:
        with path.open("a") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        log.warning("Failed to write recovery journal entry: %s", exc)


def _recovery_begin(tool_name: str, *, operation: str, context: dict[str, Any] | None = None) -> str:
    entry_id = secrets.token_hex(12)
    _write_recovery_journal_entry(
        {
            "timestamp": time.time(),
            "entry_id": entry_id,
            "tool": str(tool_name),
            "operation": str(operation),
            "status": "started",
            "context": context or {},
        }
    )
    return entry_id


def _recovery_finish(
    entry_id: str,
    *,
    tool_name: str,
    operation: str,
    status: str,
    detail: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    _write_recovery_journal_entry(
        {
            "timestamp": time.time(),
            "entry_id": str(entry_id),
            "tool": str(tool_name),
            "operation": str(operation),
            "status": str(status),
            "detail": str(detail),
            "context": context or {},
        }
    )


class _RecoveryOperation:
    def __init__(self, tool_name: str, *, operation: str, context: dict[str, Any] | None = None) -> None:
        self._tool_name = str(tool_name)
        self._operation = str(operation)
        self._base_context = dict(context or {})
        self._context_updates: dict[str, Any] = {}
        self._status = "failed"
        self._detail = ""
        self._closed = False
        self._entry_id = _recovery_begin(self._tool_name, operation=self._operation, context=self._base_context)

    def mark_completed(self, *, detail: str = "ok", context: dict[str, Any] | None = None) -> None:
        self._status = "completed"
        self._detail = str(detail)
        if context:
            self._context_updates.update(context)

    def mark_failed(self, detail: str, *, context: dict[str, Any] | None = None) -> None:
        self._status = "failed"
        self._detail = str(detail)
        if context:
            self._context_updates.update(context)

    def mark_cancelled(self, *, detail: str = "cancelled", context: dict[str, Any] | None = None) -> None:
        self._status = "cancelled"
        self._detail = str(detail)
        if context:
            self._context_updates.update(context)

    def __enter__(self) -> _RecoveryOperation:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: Any,
    ) -> bool:
        if self._closed:
            return False
        status = self._status
        detail = self._detail
        if exc is not None:
            if isinstance(exc, asyncio.CancelledError):
                status = "cancelled"
                if not detail:
                    detail = "cancelled"
            else:
                status = "failed"
                if not detail:
                    detail = exc.__class__.__name__
        if not detail:
            detail = "ok" if status == "completed" else "failed"
        context = {**self._base_context, **self._context_updates}
        _recovery_finish(
            self._entry_id,
            tool_name=self._tool_name,
            operation=self._operation,
            status=status,
            detail=detail,
            context=context,
        )
        self._closed = True
        return False


def _recovery_operation(
    tool_name: str,
    *,
    operation: str,
    context: dict[str, Any] | None = None,
) -> _RecoveryOperation:
    return _RecoveryOperation(tool_name, operation=operation, context=context)


def _recovery_reconcile_interrupted() -> None:
    entries = _read_recovery_journal_entries()
    if not entries:
        return
    latest_by_entry: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry.get("entry_id", "")).strip()
        if not entry_id:
            continue
        latest_by_entry[entry_id] = entry
    for entry_id, entry in latest_by_entry.items():
        status = str(entry.get("status", "")).strip().lower()
        if status != "started":
            continue
        _recovery_finish(
            entry_id,
            tool_name=str(entry.get("tool", "unknown")),
            operation=str(entry.get("operation", "unknown")),
            status="interrupted",
            detail="process_restart",
            context={"source": "reconcile"},
        )


def _recovery_journal_status(*, limit: int = 20) -> dict[str, Any]:
    entries = _read_recovery_journal_entries()
    latest_by_entry: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry.get("entry_id", "")).strip()
        if not entry_id:
            continue
        latest_by_entry[entry_id] = entry
    unresolved = sum(
        1
        for entry in latest_by_entry.values()
        if str(entry.get("status", "")).strip().lower() == "started"
    )
    interrupted = sum(
        1
        for entry in latest_by_entry.values()
        if str(entry.get("status", "")).strip().lower() == "interrupted"
    )
    size = max(1, min(100, int(limit)))
    recent = entries[-size:]
    return {
        "path": str(_recovery_journal_path),
        "exists": _recovery_journal_path.exists(),
        "entry_count": len(entries),
        "tracked_actions": len(latest_by_entry),
        "unresolved_count": unresolved,
        "interrupted_count": interrupted,
        "recent": recent,
    }


def _prune_audit_file(path: Path, *, cutoff_ts: float) -> int:
    if not path.exists():
        return 0
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return 0
    kept: list[str] = []
    removed = 0
    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue
        payload = _decode_audit_line(raw_line)
        if not isinstance(payload, dict):
            removed += 1
            continue
        if payload.get("encrypted") is True and payload.get("error") in {
            "missing_encryption_key",
            "invalid_token",
            "invalid_payload",
        }:
            # Do not drop encrypted lines when current process cannot decrypt.
            kept.append(raw_line)
            continue
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)) and float(ts) >= cutoff_ts:
            # Preserve original line format (encrypted/plain) on retention rewrites.
            kept.append(raw_line)
        else:
            removed += 1
    if removed <= 0:
        return 0
    try:
        if kept:
            path.write_text("\n".join(kept) + "\n")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return 0
    return removed


def _apply_retention_policies() -> None:
    now = time.time()
    if _memory is not None and _memory_retention_days > 0.0:
        cutoff = now - (_memory_retention_days * 86_400.0)
        try:
            _memory.prune_retention(cutoff_ts=cutoff)
        except Exception:
            log.warning("Failed to apply memory retention policy", exc_info=True)
    if _audit_retention_days > 0.0:
        cutoff = now - (_audit_retention_days * 86_400.0)
        paths = [AUDIT_LOG] + [AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx}") for idx in range(1, _audit_log_backups + 1)]
        for path in paths:
            removed = _prune_audit_file(path, cutoff_ts=cutoff)
            if removed > 0:
                log.info("Applied audit retention policy to %s (removed=%d)", path, removed)


def _prune_timers(now_mono: float | None = None) -> None:
    if _memory is not None:
        try:
            _memory.expire_timers(now=time.time())
        except Exception:
            log.warning("Failed to expire persisted timers", exc_info=True)
    if not _timers:
        return
    current = time.monotonic() if now_mono is None else now_mono
    expired = [timer_id for timer_id, payload in _timers.items() if float(payload.get("due_mono", 0.0)) <= current]
    for timer_id in expired:
        _timers.pop(timer_id, None)


def _timer_status() -> dict[str, Any]:
    _prune_timers()
    if not _timers:
        return {"active_count": 0, "next_due_in_sec": None}
    now = time.monotonic()
    next_due = min(float(payload.get("due_mono", now)) for payload in _timers.values())
    return {
        "active_count": len(_timers),
        "next_due_in_sec": max(0.0, next_due - now),
    }


def _load_timers_from_store() -> None:
    global _timer_id_seq
    if _memory is None:
        return
    now_wall = time.time()
    now_mono = time.monotonic()
    try:
        _memory.expire_timers(now=now_wall)
        rows = _memory.list_timers(status="active", include_expired=False, now=now_wall, limit=TIMER_MAX_ACTIVE)
    except Exception:
        log.warning("Failed to load persisted timers", exc_info=True)
        return
    max_id = 0
    for row in rows:
        remaining = float(row.due_at) - now_wall
        if remaining <= 0.0:
            continue
        timer_id = int(row.id)
        max_id = max(max_id, timer_id)
        _timers[timer_id] = {
            "id": timer_id,
            "label": row.label,
            "duration_sec": float(row.duration_sec),
            "created_at": float(row.created_at),
            "due_at": float(row.due_at),
            "due_mono": now_mono + remaining,
        }
    if max_id >= _timer_id_seq:
        _timer_id_seq = max_id + 1


def _reminder_status() -> dict[str, Any]:
    now = time.time()
    if _memory is not None:
        try:
            counts = _memory.reminder_counts()
            pending = _memory.list_reminders(status="pending", now=now, limit=REMINDER_MAX_ACTIVE)
        except Exception:
            return {"pending_count": 0, "completed_count": 0, "due_count": 0, "next_due_in_sec": None}
        due_count = sum(1 for entry in pending if float(entry.due_at) <= now)
        next_due_in = None
        if pending:
            next_due = min(float(entry.due_at) for entry in pending)
            next_due_in = max(0.0, next_due - now)
        return {
            "pending_count": int(counts.get("pending", 0)),
            "completed_count": int(counts.get("completed", 0)),
            "due_count": int(due_count),
            "next_due_in_sec": next_due_in,
        }
    pending = [payload for payload in _reminders.values() if str(payload.get("status", "pending")) == "pending"]
    completed_count = sum(
        1 for payload in _reminders.values() if str(payload.get("status", "pending")) == "completed"
    )
    due_count = sum(1 for payload in pending if float(payload.get("due_at", 0.0)) <= now)
    next_due_in = None
    if pending:
        next_due = min(float(payload.get("due_at", now)) for payload in pending)
        next_due_in = max(0.0, next_due - now)
    return {
        "pending_count": len(pending),
        "completed_count": int(completed_count),
        "due_count": int(due_count),
        "next_due_in_sec": next_due_in,
    }


def _load_reminders_from_store() -> None:
    global _reminder_id_seq
    if _memory is None:
        return
    now = time.time()
    try:
        pending = _memory.list_reminders(status="pending", now=now, limit=REMINDER_MAX_ACTIVE)
        completed = _memory.list_reminders(status="completed", limit=REMINDER_MAX_ACTIVE)
    except Exception:
        log.warning("Failed to load persisted reminders", exc_info=True)
        return
    max_id = 0
    for row in [*pending, *completed]:
        reminder_id = int(row.id)
        max_id = max(max_id, reminder_id)
        _reminders[reminder_id] = {
            "id": reminder_id,
            "text": str(row.text),
            "due_at": float(row.due_at),
            "created_at": float(row.created_at),
            "status": str(row.status),
            "completed_at": float(row.completed_at) if row.completed_at is not None else None,
            "notified_at": float(row.notified_at) if row.notified_at is not None else None,
        }
    if max_id >= _reminder_id_seq:
        _reminder_id_seq = max_id + 1


def _ha_headers() -> dict[str, str]:
    assert _config is not None
    return {"Authorization": f"Bearer {_config.hass_token}"}


def _ha_cached_state(entity_id: str) -> dict[str, Any] | None:
    item = _ha_state_cache.get(entity_id)
    if item is None:
        return None
    expires_at, payload = item
    if expires_at < time.monotonic():
        _ha_state_cache.pop(entity_id, None)
        return None
    return payload


def _ha_invalidate_state(entity_id: str) -> None:
    _ha_state_cache.pop(entity_id, None)


def _ha_action_allowed(domain: str, action: str) -> bool:
    allowed = HA_MUTATING_ALLOWED_ACTIONS.get(domain)
    if allowed is None:
        return False
    return action in allowed


async def _ha_get_state(entity_id: str) -> tuple[dict[str, Any] | None, str | None]:
    if _integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    cached = _ha_cached_state(entity_id)
    if cached is not None:
        return cached, None
    assert _config is not None
    url = f"{_config.hass_url}/api/states/{entity_id}"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(5.0))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=_ha_headers()) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, dict):
                        return None, "invalid_json"
                    _ha_state_cache[entity_id] = (time.monotonic() + HA_STATE_CACHE_TTL_SEC, data)
                    _integration_record_success("home_assistant")
                    return data, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def _ha_get_domain_services(domain: str) -> tuple[list[str] | None, str | None]:
    if _integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert _config is not None
    url = f"{_config.hass_url}/api/services"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(5.0))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=_ha_headers()) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, list):
                        return None, "invalid_json"
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("domain", "")).strip().lower() != domain:
                            continue
                        raw_services = item.get("services")
                        if not isinstance(raw_services, dict):
                            return [], None
                        names = sorted(
                            {
                                str(name).strip()
                                for name in raw_services.keys()
                                if str(name).strip()
                            }
                        )
                        _integration_record_success("home_assistant")
                        return names, None
                    _integration_record_success("home_assistant")
                    return [], None
                if resp.status == 401:
                    return None, "auth"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def _ha_call_service(
    domain: str,
    service: str,
    service_data: dict[str, Any],
    *,
    return_response: bool = False,
    timeout_sec: float = 10.0,
) -> tuple[list[Any] | None, str | None]:
    if _integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert _config is not None
    suffix = "?return_response" if return_response else ""
    url = f"{_config.hass_url}/api/services/{domain}/{service}{suffix}"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec))
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=service_data) as resp:
                if resp.status in {200, 201}:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, list):
                        return None, "invalid_json"
                    _integration_record_success("home_assistant")
                    return data, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def _ha_get_json(
    path: str,
    *,
    params: dict[str, str] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    if _integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert _config is not None
    url = f"{_config.hass_url}{path}"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=_ha_headers(), params=params or None) as resp:
                if resp.status == 200:
                    try:
                        payload = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    _integration_record_success("home_assistant")
                    return payload, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def _ha_render_template(template_text: str, *, timeout_sec: float = 10.0) -> tuple[str | None, str | None]:
    if _integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert _config is not None
    url = f"{_config.hass_url}/api/template"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec))
    headers = {**_ha_headers(), "Content-Type": "text/plain"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, data=template_text) as resp:
                if resp.status == 200:
                    try:
                        payload = await resp.text()
                    except Exception:
                        return None, "invalid_json"
                    _integration_record_success("home_assistant")
                    return payload, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


def _collect_json_lists_by_key(value: Any, key: str) -> list[Any]:
    results: list[Any] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key and isinstance(item_value, list):
                results.extend(item_value)
            else:
                results.extend(_collect_json_lists_by_key(item_value, key))
    elif isinstance(value, list):
        for item in value:
            results.extend(_collect_json_lists_by_key(item, key))
    return results


def _parse_calendar_event_timestamp(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    parsed = _parse_datetime_text(value)
    if parsed is None:
        return None
    return parsed.timestamp()


def _webhook_host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if not _webhook_allowlist:
        return False
    for allowed in _webhook_allowlist:
        if host == allowed:
            return True
        if host.endswith(f".{allowed}"):
            return True
    return False


def record_inbound_webhook_event(
    *,
    payload: Any,
    headers: dict[str, Any] | None = None,
    source: str = "unknown",
    path: str = "/",
) -> int:
    global _inbound_webhook_seq
    event_id = _inbound_webhook_seq
    _inbound_webhook_seq += 1
    entry = {
        "id": event_id,
        "timestamp": time.time(),
        "source": str(source),
        "path": str(path),
        "headers": _sanitize_inbound_headers(headers),
        "payload": _sanitize_inbound_payload(payload),
    }
    _inbound_webhook_events.append(entry)
    if len(_inbound_webhook_events) > 500:
        del _inbound_webhook_events[:-500]
    _audit(
        "webhook_inbound",
        {
            "result": "ok",
            "event_id": event_id,
            "source": entry["source"],
            "path": entry["path"],
            "header_count": len(entry["headers"]),
        },
    )
    return event_id


def _integration_health_snapshot() -> dict[str, Any]:
    home_configured = bool(_config and _config.has_home_assistant)
    todoist_configured = bool(_config and str(_config.todoist_api_token).strip())
    pushover_configured = bool(_config and str(_config.pushover_api_token).strip() and str(_config.pushover_user_key).strip())
    return {
        "home_assistant": {
            "configured": home_configured,
            "home_enabled": bool(_config and _config.home_enabled),
            "permission_profile": _home_permission_profile,
            "circuit_breaker": _integration_circuit_snapshot("home_assistant"),
        },
        "todoist": {
            "configured": todoist_configured,
            "permission_profile": _todoist_permission_profile,
            "circuit_breaker": _integration_circuit_snapshot("todoist"),
        },
        "pushover": {
            "configured": pushover_configured,
            "permission_profile": _notification_permission_profile,
            "circuit_breaker": _integration_circuit_snapshot("pushover"),
        },
        "weather": {
            "provider": "open-meteo",
            "units_default": _weather_units,
            "timeout_sec": _weather_timeout_sec,
            "circuit_breaker": _integration_circuit_snapshot("weather"),
        },
        "webhook": {
            "allowlist_count": len(_webhook_allowlist),
            "auth_token_configured": bool(_webhook_auth_token),
            "timeout_sec": _webhook_timeout_sec,
            "inbound_events": len(_inbound_webhook_events),
            "circuit_breaker": _integration_circuit_snapshot("webhook"),
        },
        "email": {
            "configured": bool(_email_smtp_host and _email_from and _email_default_to),
            "permission_profile": _email_permission_profile,
            "timeout_sec": _email_timeout_sec,
            "circuit_breaker": _integration_circuit_snapshot("email"),
        },
        "channels": {
            "slack_configured": bool(_slack_webhook_url),
            "discord_configured": bool(_discord_webhook_url),
            "circuit_breaker": _integration_circuit_snapshot("channels"),
        },
    }


def _identity_status_snapshot() -> dict[str, Any]:
    return {
        "enabled": _identity_enforcement_enabled,
        "default_user": _identity_default_user,
        "default_profile": _identity_default_profile,
        "require_approval": _identity_require_approval,
        "approval_code_configured": bool(_identity_approval_code),
        "trusted_user_count": len(_identity_trusted_users),
        "trusted_users": sorted(_identity_trusted_users),
        "profile_count": len(_identity_user_profiles),
        "user_profiles": {user: _identity_user_profiles[user] for user in sorted(_identity_user_profiles)},
    }


def _voice_attention_snapshot() -> dict[str, Any]:
    default_choreography = {
        "phase": "idle",
        "label": "idle_reset",
        "turn_lean": 0.0,
        "turn_tilt": 0.0,
        "turn_glance_yaw": 0.0,
        "updated_at": 0.0,
    }
    default_stt_diagnostics = {
        "source": "none",
        "fallback_used": False,
        "confidence_score": 0.0,
        "confidence_band": "unknown",
        "avg_logprob": -3.0,
        "avg_no_speech_prob": 1.0,
        "language": "unknown",
        "language_probability": 0.0,
        "segment_count": 0,
        "word_count": 0,
        "char_count": 0,
        "updated_at": 0.0,
        "error": "",
    }
    if not _runtime_voice_state:
        return {
            "mode": "unknown",
            "followup_active": False,
            "sleeping": False,
            "active_room": "unknown",
            "silence_timeout_sec": 0.0,
            "adaptive_silence_timeout_sec": 0.0,
            "speech_rate_wps": 0.0,
            "interruption_likelihood": 0.0,
            "turn_choreography": default_choreography,
            "stt_diagnostics": default_stt_diagnostics,
        }
    snapshot = {str(key): value for key, value in _runtime_voice_state.items()}
    snapshot.setdefault("silence_timeout_sec", 0.0)
    snapshot.setdefault("adaptive_silence_timeout_sec", float(snapshot.get("silence_timeout_sec", 0.0) or 0.0))
    snapshot.setdefault("speech_rate_wps", 0.0)
    snapshot.setdefault("interruption_likelihood", 0.0)
    if not isinstance(snapshot.get("turn_choreography"), dict):
        snapshot["turn_choreography"] = default_choreography
    if not isinstance(snapshot.get("stt_diagnostics"), dict):
        snapshot["stt_diagnostics"] = default_stt_diagnostics
    else:
        stt_diag = {str(key): value for key, value in snapshot["stt_diagnostics"].items()}
        for key, value in default_stt_diagnostics.items():
            stt_diag.setdefault(key, value)
        snapshot["stt_diagnostics"] = stt_diag
    return snapshot


def _observability_snapshot() -> dict[str, Any]:
    default_intent_metrics = {
        "turn_count": 0.0,
        "answer_intent_count": 0.0,
        "action_intent_count": 0.0,
        "hybrid_intent_count": 0.0,
        "answer_sample_count": 0.0,
        "completion_sample_count": 0.0,
        "answer_quality_success_rate": 0.0,
        "completion_success_rate": 0.0,
        "correction_count": 0.0,
        "correction_frequency": 0.0,
    }
    if not _runtime_observability_state:
        return {
            "enabled": False,
            "uptime_sec": 0.0,
            "restart_count": 0,
            "alerts": [],
            "intent_metrics": default_intent_metrics,
        }
    snapshot = {str(key): value for key, value in _runtime_observability_state.items()}
    if not isinstance(snapshot.get("intent_metrics"), dict):
        snapshot["intent_metrics"] = default_intent_metrics
    return snapshot


def _skills_status_snapshot() -> dict[str, Any]:
    if not _runtime_skills_state:
        if _skill_registry is not None:
            return _skill_registry.status_snapshot()
        return {
            "enabled": False,
            "loaded_count": 0,
            "enabled_count": 0,
            "skills": [],
        }
    return {str(key): value for key, value in _runtime_skills_state.items()}


def _health_rollup(
    *,
    config_present: bool,
    memory_status: dict[str, Any] | None,
    recent_tools: list[dict[str, object]] | dict[str, str],
    identity_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    level = "ok"
    if not config_present:
        level = "error"
        reasons.append("config_unbound")
    if isinstance(memory_status, dict) and "error" in memory_status:
        reasons.append("memory_error")
    if isinstance(recent_tools, dict) and "error" in recent_tools:
        reasons.append("tool_summary_error")
    if isinstance(identity_status, dict):
        if (
            bool(identity_status.get("enabled"))
            and bool(identity_status.get("require_approval"))
            and not bool(identity_status.get("approval_code_configured"))
            and int(identity_status.get("trusted_user_count", 0) or 0) <= 0
        ):
            reasons.append("identity_approval_unconfigured")
    if reasons and level != "error":
        level = "degraded"
    return {"health_level": level, "reasons": reasons}


def _score_label(score: float) -> str:
    value = _as_float(score, 0.0, minimum=0.0, maximum=1.0)
    if value >= 0.9:
        return "excellent"
    if value >= 0.75:
        return "strong"
    if value >= 0.6:
        return "fair"
    return "weak"


def _recent_tool_rows(recent_tools: list[dict[str, object]] | dict[str, str] | Any) -> list[dict[str, object]]:
    if not isinstance(recent_tools, list):
        return []
    rows: list[dict[str, object]] = []
    for row in recent_tools:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _duration_p95_ms(rows: list[dict[str, object]]) -> float:
    durations: list[float] = []
    for row in rows:
        try:
            value = float(row.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        if math.isfinite(value) and value >= 0.0:
            durations.append(value)
    if not durations:
        return 0.0
    ordered = sorted(durations)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[index]


def _jarvis_scorecard_snapshot(
    *,
    recent_tools: list[dict[str, object]] | dict[str, str],
    health: dict[str, Any],
    observability: dict[str, Any],
    identity: dict[str, Any],
    tool_policy: dict[str, Any],
    audit: dict[str, Any],
    integrations: dict[str, Any],
) -> dict[str, Any]:
    rows = _recent_tool_rows(recent_tools)

    p95_ms = _duration_p95_ms(rows)
    latency_score = 0.75 if p95_ms <= 0.0 else max(0.0, min(1.0, 1.0 - (p95_ms / 4000.0)))

    success_statuses = {"ok", "dry_run", "noop", "cooldown", "empty"}
    failure_statuses = {"error", "denied"}
    success_count = 0
    failure_count = 0
    for row in rows:
        status = str(row.get("status", "")).strip().lower()
        if status in success_statuses:
            success_count += 1
        elif status in failure_statuses:
            failure_count += 1
    total_scored = success_count + failure_count
    success_rate = (success_count / total_scored) if total_scored > 0 else 0.85
    reliability_score = success_rate
    health_level = str(health.get("health_level", "ok")).strip().lower()
    if health_level == "degraded":
        reliability_score -= 0.08
    elif health_level == "error":
        reliability_score -= 0.20
    open_breakers = 0
    if isinstance(integrations, dict):
        for payload in integrations.values():
            if not isinstance(payload, dict):
                continue
            breaker = payload.get("circuit_breaker")
            if isinstance(breaker, dict) and bool(breaker.get("open")):
                open_breakers += 1
    reliability_score -= min(0.25, open_breakers * 0.05)
    reliability_score = _as_float(reliability_score, 0.0, minimum=0.0, maximum=1.0)

    intent = observability.get("intent_metrics") if isinstance(observability, dict) else None
    intent_payload = intent if isinstance(intent, dict) else {}
    turn_count = _as_float(intent_payload.get("turn_count", 0.0), 0.0, minimum=0.0)
    action_count = _as_float(intent_payload.get("action_intent_count", 0.0), 0.0, minimum=0.0)
    hybrid_count = _as_float(intent_payload.get("hybrid_intent_count", 0.0), 0.0, minimum=0.0)
    completion_success = _as_float(intent_payload.get("completion_success_rate", 0.0), 0.0, minimum=0.0, maximum=1.0)
    correction_frequency = _as_float(intent_payload.get("correction_frequency", 0.0), 0.0, minimum=0.0, maximum=1.0)
    if turn_count <= 0.0:
        action_or_hybrid_ratio = 0.0
        initiative_score = 0.50
    else:
        action_or_hybrid_ratio = max(0.0, min(1.0, (action_count + hybrid_count) / turn_count))
        action_signal = min(1.0, action_or_hybrid_ratio / 0.35)
        correction_signal = max(0.0, 1.0 - min(1.0, correction_frequency / 0.25))
        initiative_score = (0.45 * completion_success) + (0.35 * action_signal) + (0.20 * correction_signal)
    initiative_score = _as_float(initiative_score, 0.0, minimum=0.0, maximum=1.0)

    identity_enabled = bool(identity.get("enabled")) if isinstance(identity, dict) else False
    require_approval = bool(identity.get("require_approval")) if isinstance(identity, dict) else False
    trusted_users = _as_int(identity.get("trusted_user_count", 0), 0, minimum=0) if isinstance(identity, dict) else 0
    approval_code_configured = bool(identity.get("approval_code_configured")) if isinstance(identity, dict) else False
    approval_configured = approval_code_configured or trusted_users > 0
    safe_mode_enabled = bool(tool_policy.get("safe_mode_enabled")) if isinstance(tool_policy, dict) else False
    plan_preview_ack = bool(tool_policy.get("plan_preview_require_ack")) if isinstance(tool_policy, dict) else False
    audit_redaction = bool(audit.get("redaction_enabled")) if isinstance(audit, dict) else False
    audit_encrypted = bool(audit.get("encrypted")) if isinstance(audit, dict) else False
    trust_score = 0.30
    trust_score += 0.20 if identity_enabled else 0.08
    trust_score += 0.14 if require_approval and approval_configured else (0.04 if require_approval else 0.10)
    trust_score += 0.10 if plan_preview_ack else 0.04
    trust_score += 0.12 if audit_redaction else 0.0
    trust_score += 0.06 if audit_encrypted else 0.0
    trust_score += 0.06 if safe_mode_enabled else 0.0
    if require_approval and not approval_configured:
        trust_score -= 0.15
    trust_score = _as_float(trust_score, 0.0, minimum=0.0, maximum=1.0)

    weights = {
        "latency": 0.30,
        "reliability": 0.30,
        "initiative": 0.20,
        "trust": 0.20,
    }
    overall_score = (
        (weights["latency"] * latency_score)
        + (weights["reliability"] * reliability_score)
        + (weights["initiative"] * initiative_score)
        + (weights["trust"] * trust_score)
    )
    overall_score = _as_float(overall_score, 0.0, minimum=0.0, maximum=1.0)

    return {
        "overall": {
            "score": round(overall_score, 4),
            "grade": _score_label(overall_score),
        },
        "dimensions": {
            "latency": {
                "score": round(latency_score, 4),
                "grade": _score_label(latency_score),
                "p95_ms": round(p95_ms, 2),
                "sample_count": len(rows),
            },
            "reliability": {
                "score": round(reliability_score, 4),
                "grade": _score_label(reliability_score),
                "success_rate": round(_as_float(success_rate, 0.0, minimum=0.0, maximum=1.0), 4),
                "failure_rate": round(1.0 - _as_float(success_rate, 0.0, minimum=0.0, maximum=1.0), 4),
                "open_circuit_breakers": open_breakers,
            },
            "initiative": {
                "score": round(initiative_score, 4),
                "grade": _score_label(initiative_score),
                "completion_success_rate": round(completion_success, 4),
                "action_or_hybrid_ratio": round(action_or_hybrid_ratio, 4),
                "correction_frequency": round(correction_frequency, 4),
            },
            "trust": {
                "score": round(trust_score, 4),
                "grade": _score_label(trust_score),
                "identity_enabled": identity_enabled,
                "approval_required": require_approval,
                "approval_configured": approval_configured,
                "safe_mode_enabled": safe_mode_enabled,
                "plan_preview_ack_required": plan_preview_ack,
                "audit_redaction_enabled": audit_redaction,
                "audit_encrypted": audit_encrypted,
            },
        },
        "weights": weights,
        "computed_at": time.time(),
    }


# ── Home Assistant ────────────────────────────────────────────

async def smart_home(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("smart_home"):
        record_summary("smart_home", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        _record_service_error("smart_home", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    domain = str(args.get("domain", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    data = args.get("data", {})
    if not domain or not entity_id:
        _record_service_error("smart_home", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Domain and entity_id are required."}]}
    if not action or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in action):
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Action must be a non-empty snake_case service name."}]}
    if not isinstance(data, dict):
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Service data must be an object."}]}
    if domain not in HA_MUTATING_ALLOWED_ACTIONS:
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Unsupported domain for smart_home: {domain}"}]}
    entity_domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    if not entity_domain or entity_domain != domain:
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "entity_id domain must match domain."}]}
    if not _ha_action_allowed(domain, action):
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Unsupported action for domain: {domain}.{action}"}]}
    # Force dry_run for sensitive domains unless explicitly set to false
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
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
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
        return {"content": [{"type": "text", "text": "Action requires confirm=true when HOME_REQUIRE_CONFIRM_EXECUTE=true."}]}
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
        return {"content": [{"type": "text", "text": "Sensitive action requires confirm=true when dry_run=false."}]}
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
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Ambiguous high-risk target. Specify one explicit entity instead of a broad/group target.",
                }
            ]
        }
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
            enforce_default=_plan_preview_require_ack,
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
            return {"content": [{"type": "text", "text": preview}]}

    current_state = "unknown"
    if not dry_run:
        if _cooldown_active(domain, action, entity_id):
            tool_feedback("done")
            record_summary("smart_home", "cooldown", start_time)
            return {"content": [{"type": "text", "text": "Action cooldown active. Try again in a moment."}]}

        state_payload, state_error = await _ha_get_state(entity_id)
        if state_error is not None:
            _record_service_error("smart_home", start_time, state_error)
            if state_error == "not_found":
                return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
            if state_error == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if state_error == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant state preflight timed out."}]}
            if state_error == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant state preflight was cancelled."}]}
            if state_error == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if state_error == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant for state preflight."}]}
            return {"content": [{"type": "text", "text": "Unable to validate entity state before action."}]}

        current_state = str(state_payload.get("state", "unknown")) if isinstance(state_payload, dict) else "unknown"
        if action == "turn_on" and current_state not in {"off", "unavailable", "unknown"}:
            record_summary("smart_home", "noop", start_time, effect=f"already_on {entity_id}", risk="low")
            return {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}
        if action == "turn_off" and current_state == "off":
            record_summary("smart_home", "noop", start_time, effect=f"already_off {entity_id}", risk="low")
            return {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}

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
                "state": current_state,
                "policy_decision": "dry_run" if dry_run else "allowed",
            },
            identity_context,
            [*identity_chain, "decision:dry_run" if dry_run else "decision:execute"],
        ),
    )

    if dry_run:
        tool_feedback("start")
        tool_feedback("done")
        record_summary(
            "smart_home",
            "dry_run",
            start_time,
            effect=f"no-op {domain}.{action} {entity_id}",
            risk="low",
        )
        return {"content": [{"type": "text", "text": (
            f"DRY RUN: Would call {domain}.{action} on {entity_id}"
            f"{' with ' + json.dumps(data, default=str) if data else ''}. "
            f"{'Safe mode forced dry-run. ' if safe_mode_forced else ''}"
            f"Set dry_run=false to execute."
        )}]}

    url = f"{_config.hass_url}/api/services/{domain}/{action}"
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    payload = {"entity_id": entity_id, **data}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(10.0))
    with _recovery_operation(
        "smart_home",
        operation=f"{domain}.{action}",
        context={"entity_id": entity_id, "domain": domain},
    ) as recovery:
        try:
            tool_feedback("start")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        tool_feedback("done")
                        _ha_invalidate_state(entity_id)
                        _touch_action(domain, action, entity_id)
                        _integration_record_success("home_assistant")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary(
                            "smart_home",
                            "ok",
                            start_time,
                            effect=f"executed {domain}.{action} {entity_id}",
                            risk="medium" if domain in SENSITIVE_DOMAINS else "low",
                        )
                        return {"content": [{"type": "text", "text": f"Done: {domain}.{action} on {entity_id}"}]}
                    if resp.status == 401:
                        tool_feedback("done")
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("smart_home", start_time, "auth")
                        return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                    if resp.status == 404:
                        tool_feedback("done")
                        recovery.mark_failed("not_found", context={"http_status": resp.status})
                        _record_service_error("smart_home", start_time, "not_found")
                        return {"content": [{"type": "text", "text": f"Service not found: {domain}.{action}"}]}
                    try:
                        text = await resp.text()
                    except Exception:
                        text = "<body unavailable>"
                    tool_feedback("done")
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("smart_home", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Home Assistant error ({resp.status}): {text[:200]}"}]}
        except asyncio.TimeoutError:
            tool_feedback("done")
            recovery.mark_failed("timeout")
            _record_service_error("smart_home", start_time, "timeout")
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        except asyncio.CancelledError:
            tool_feedback("done")
            recovery.mark_cancelled()
            _record_service_error("smart_home", start_time, "cancelled")
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        except aiohttp.ClientError as e:
            tool_feedback("done")
            recovery.mark_failed("network_client_error")
            _record_service_error("smart_home", start_time, "network_client_error")
            return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}
        except Exception:
            tool_feedback("done")
            recovery.mark_failed("unexpected")
            _record_service_error("smart_home", start_time, "unexpected")
            log.exception("Unexpected smart_home failure")
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}


async def smart_home_state(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("smart_home_state"):
        record_summary("smart_home_state", "denied", start_time, "policy")
        _audit("smart_home_state", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        _record_service_error("smart_home_state", start_time, "missing_config")
        _audit("smart_home_state", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured."}]}

    entity_id = str(args.get("entity_id", "")).strip().lower()
    if not entity_id:
        _record_service_error("smart_home_state", start_time, "missing_entity")
        _audit("smart_home_state", {"result": "missing_entity"})
        return {"content": [{"type": "text", "text": "Entity id required."}]}
    tool_feedback("start")
    data, error_code = await _ha_get_state(entity_id)
    tool_feedback("done")
    if error_code is not None:
        _record_service_error("smart_home_state", start_time, error_code)
        _audit("smart_home_state", {"result": error_code, "entity_id": entity_id})
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid response from Home Assistant."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}
    payload = data or {}
    record_summary("smart_home_state", "ok", start_time)
    _audit(
        "smart_home_state",
        {
            "result": "ok",
            "entity_id": entity_id,
            "state": payload.get("state", "unknown"),
        },
    )
    return {"content": [{"type": "text", "text": json.dumps({
        "state": payload.get("state", "unknown"),
        "attributes": payload.get("attributes", {}),
    })}]}


async def home_assistant_capabilities(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_capabilities"):
        record_summary("home_assistant_capabilities", "denied", start_time, "policy")
        _audit("home_assistant_capabilities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_capabilities", start_time, "missing_config")
        _audit("home_assistant_capabilities", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    entity_id = str(args.get("entity_id", "")).strip().lower()
    if not entity_id:
        _record_service_error("home_assistant_capabilities", start_time, "missing_entity")
        _audit("home_assistant_capabilities", {"result": "missing_entity"})
        return {"content": [{"type": "text", "text": "Entity id required."}]}
    include_services = _as_bool(args.get("include_services"), default=True)

    state_payload, state_error = await _ha_get_state(entity_id)
    if state_error is not None:
        _record_service_error("home_assistant_capabilities", start_time, state_error)
        _audit("home_assistant_capabilities", {"result": state_error, "entity_id": entity_id})
        if state_error == "not_found":
            return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if state_error == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if state_error == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid response from Home Assistant."}]}
        if state_error == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        if state_error == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        if state_error == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if state_error == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}

    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    services_for_domain: list[str] = []
    if include_services and domain:
        service_names, service_error = await _ha_get_domain_services(domain)
        if service_error is not None:
            _record_service_error("home_assistant_capabilities", start_time, service_error)
            _audit(
                "home_assistant_capabilities",
                {
                    "result": service_error,
                    "entity_id": entity_id,
                    "domain": domain,
                    "phase": "service_catalog",
                },
            )
            if service_error == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed while reading services."}]}
            if service_error == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant service catalog response."}]}
            if service_error == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant service catalog request timed out."}]}
            if service_error == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant service catalog request was cancelled."}]}
            if service_error == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if service_error == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant service catalog endpoint."}]}
            return {"content": [{"type": "text", "text": "Unable to fetch Home Assistant service catalog."}]}
        services_for_domain = service_names or []

    payload = state_payload or {}
    result = {
        "entity_id": entity_id,
        "domain": domain,
        "state": payload.get("state", "unknown"),
        "attributes": payload.get("attributes", {}),
        "available_services": services_for_domain,
    }
    record_summary("home_assistant_capabilities", "ok", start_time)
    _audit(
        "home_assistant_capabilities",
        {
            "result": "ok",
            "entity_id": entity_id,
            "domain": domain,
            "include_services": include_services,
            "service_count": len(services_for_domain),
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


def _ha_conversation_speech(payload: dict[str, Any]) -> str:
    response = payload.get("response")
    if not isinstance(response, dict):
        return ""
    speech = response.get("speech")
    if not isinstance(speech, dict):
        return ""
    plain = speech.get("plain")
    if isinstance(plain, dict):
        text = str(plain.get("speech", "")).strip()
        if text:
            return text
    text = str(speech.get("speech", "")).strip()
    if text:
        return text
    return ""


async def home_assistant_conversation(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_conversation"):
        record_summary("home_assistant_conversation", "denied", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_conversation", start_time, "missing_config")
        _audit("home_assistant_conversation", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("home_assistant")
    if circuit_open:
        _record_service_error("home_assistant_conversation", start_time, "circuit_open")
        _audit("home_assistant_conversation", {"result": "circuit_open"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": _integration_circuit_open_message("home_assistant", circuit_remaining),
                }
            ]
        }
    if not _home_conversation_enabled:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "conversation_disabled"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant conversation tool is disabled. Set HOME_CONVERSATION_ENABLED=true to enable.",
                }
            ]
        }
    if _home_conversation_permission_profile != "control":
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "conversation_readonly_profile"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant conversation requires HOME_CONVERSATION_PERMISSION_PROFILE=control.",
                }
            ]
        }
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("home_assistant_conversation", start_time, "missing_fields")
        _audit("home_assistant_conversation", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Conversation text is required."}]}
    if len(text) > HA_CONVERSATION_MAX_TEXT_CHARS:
        _record_service_error("home_assistant_conversation", start_time, "invalid_data")
        _audit("home_assistant_conversation", {"result": "invalid_data", "field": "text_length", "length": len(text)})
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Conversation text exceeds {HA_CONVERSATION_MAX_TEXT_CHARS} characters.",
                }
            ]
        }
    if _is_ambiguous_high_risk_text(text):
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "ambiguous_high_risk_text"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "That risky command is ambiguous. Name the exact target entity/device before execution.",
                }
            ]
        }
    confirm = _as_bool(args.get("confirm"), default=False)
    if not confirm:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "confirm_required", "text_length": len(text)})
        return {"content": [{"type": "text", "text": "Set confirm=true to execute a Home Assistant conversation command."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_conversation",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit(
            "home_assistant_conversation",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "text_length": len(text)},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    preview = _preview_gate(
        tool_name="home_assistant_conversation",
        args=args,
        risk="high",
        summary=f"conversation command: {text[:120]}",
        signature_payload={
            "text": text,
            "language": str(args.get("language", "")).strip(),
            "agent_id": str(args.get("agent_id", "")).strip(),
        },
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("home_assistant_conversation", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "home_assistant_conversation",
            _identity_enriched_audit(
                {"result": "preview_required", "text_length": len(text)},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}

    payload: dict[str, Any] = {"text": text}
    language = str(args.get("language", "")).strip()
    if language:
        payload["language"] = language
    agent_id = str(args.get("agent_id", "")).strip()
    if agent_id:
        payload["agent_id"] = agent_id
    url = f"{_config.hass_url}/api/conversation/process"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(10.0))
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    with _recovery_operation(
        "home_assistant_conversation",
        operation="conversation_process",
        context={"text_length": len(text)},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        try:
                            body = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("home_assistant_conversation", start_time, "invalid_json")
                            _audit("home_assistant_conversation", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Home Assistant conversation response."}]}
                        if not isinstance(body, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("home_assistant_conversation", start_time, "invalid_json")
                            _audit("home_assistant_conversation", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Home Assistant conversation response."}]}
                        response_type = ""
                        response = body.get("response")
                        if isinstance(response, dict):
                            response_type = str(response.get("response_type", "")).strip()
                        speech = _ha_conversation_speech(body)
                        if not speech:
                            speech = "Home Assistant processed the command."
                        conversation_id = str(body.get("conversation_id", "")).strip()
                        _integration_record_success("home_assistant")
                        recovery.mark_completed(
                            detail="ok",
                            context={
                                "response_type": response_type,
                                "conversation_id": conversation_id,
                            },
                        )
                        record_summary("home_assistant_conversation", "ok", start_time)
                        _audit(
                            "home_assistant_conversation",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "response_type": response_type,
                                    "conversation_id": conversation_id,
                                    "text_length": len(text),
                                    "language": language,
                                    "agent_id": agent_id,
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        suffix = ""
                        if response_type:
                            suffix += f" [type={response_type}]"
                        if conversation_id:
                            suffix += f" [conversation_id={conversation_id}]"
                        return {"content": [{"type": "text", "text": f"{speech}{suffix}"}]}
                    if resp.status == 401:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("home_assistant_conversation", start_time, "auth")
                        _audit("home_assistant_conversation", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                    if resp.status == 404:
                        recovery.mark_failed("not_found", context={"http_status": resp.status})
                        _record_service_error("home_assistant_conversation", start_time, "not_found")
                        _audit("home_assistant_conversation", {"result": "not_found"})
                        return {"content": [{"type": "text", "text": "Home Assistant conversation endpoint not found."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("home_assistant_conversation", start_time, "http_error")
                    _audit("home_assistant_conversation", {"result": "http_error", "status": resp.status})
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Home Assistant conversation error ({resp.status}).",
                            }
                        ]
                    }
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("home_assistant_conversation", start_time, "timeout")
            _audit("home_assistant_conversation", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Home Assistant conversation request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("home_assistant_conversation", start_time, "cancelled")
            _audit("home_assistant_conversation", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Home Assistant conversation request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("home_assistant_conversation", start_time, "network_client_error")
            _audit("home_assistant_conversation", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant conversation endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("home_assistant_conversation", start_time, "unexpected")
            _audit("home_assistant_conversation", {"result": "unexpected"})
            log.exception("Unexpected home_assistant_conversation failure")
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant conversation error."}]}


async def home_assistant_todo(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_todo"):
        record_summary("home_assistant_todo", "denied", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_todo", start_time, "missing_config")
        _audit("home_assistant_todo", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"list", "add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "invalid_data")
        _audit("home_assistant_todo", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: list, add, remove."}]}
    if not entity_id:
        _record_service_error("home_assistant_todo", start_time, "missing_fields")
        _audit("home_assistant_todo", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_todo",
        args,
        mutating=(action in {"add", "remove"}),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit(
            "home_assistant_todo",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action in {"add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "list":
        payload, error_code = await _ha_call_service(
            "todo",
            "get_items",
            {
                "entity_id": entity_id,
                **(
                    {"status": str(args.get("status", "")).strip()}
                    if str(args.get("status", "")).strip()
                    else {}
                ),
            },
            return_response=True,
        )
        if error_code is not None:
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"To-do entity or service not found: {entity_id}"}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        items = [item for item in _collect_json_lists_by_key(payload, "items") if isinstance(item, dict)]
        if not items:
            record_summary("home_assistant_todo", "empty", start_time)
            _audit("home_assistant_todo", {"result": "empty", "action": action, "entity_id": entity_id})
            return {"content": [{"type": "text", "text": "No Home Assistant to-do items found."}]}
        lines: list[str] = []
        for item in items:
            summary = str(item.get("summary") or item.get("item") or "").strip() or "(untitled)"
            uid = str(item.get("uid") or item.get("id") or "").strip()
            status = str(item.get("status", "")).strip()
            due = str(item.get("due") or item.get("due_datetime") or "").strip()
            meta: list[str] = []
            if uid:
                meta.append(f"id={uid}")
            if status:
                meta.append(f"status={status}")
            if due:
                meta.append(f"due={due}")
            lines.append(f"- {summary}" + (f" ({'; '.join(meta)})" if meta else ""))
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {"result": "ok", "action": action, "entity_id": entity_id, "count": len(lines)},
        )
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    item = str(args.get("item", "")).strip()
    item_id = str(args.get("item_id", "")).strip()
    if action == "add":
        if not item:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item is required when action=add."}]}
        service = "add_item"
        service_data = {"entity_id": entity_id, "item": item}
        success_text = "Added Home Assistant to-do item."
    else:
        if not item and not item_id:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item or item_id is required when action=remove."}]}
        service = "remove_item"
        service_data = {"entity_id": entity_id, "item": item_id or item}
        success_text = "Removed Home Assistant to-do item."

    with _recovery_operation(
        "home_assistant_todo",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("todo", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant to-do entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {
                "result": "ok",
                "action": action,
                "entity_id": entity_id,
                "item_length": len(item),
                "item_id": item_id,
            },
        )
        return {"content": [{"type": "text", "text": success_text}]}


async def home_assistant_timer(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_timer"):
        record_summary("home_assistant_timer", "denied", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_timer", start_time, "missing_config")
        _audit("home_assistant_timer", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"state", "start", "pause", "cancel", "finish"}:
        _record_service_error("home_assistant_timer", start_time, "invalid_data")
        _audit("home_assistant_timer", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: state, start, pause, cancel, finish."}]}
    if not entity_id:
        _record_service_error("home_assistant_timer", start_time, "missing_fields")
        _audit("home_assistant_timer", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_timer",
        args,
        mutating=(action != "state"),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit(
            "home_assistant_timer",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action != "state":
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "state":
        payload, error_code = await _ha_get_state(entity_id)
        if error_code is not None:
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"Timer not found: {entity_id}"}]}
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        body = payload or {}
        attributes = body.get("attributes", {}) if isinstance(body, dict) else {}
        result = {
            "entity_id": entity_id,
            "state": body.get("state", "unknown") if isinstance(body, dict) else "unknown",
            "remaining": attributes.get("remaining") if isinstance(attributes, dict) else None,
            "duration": attributes.get("duration") if isinstance(attributes, dict) else None,
            "finishes_at": attributes.get("finishes_at") if isinstance(attributes, dict) else None,
        }
        record_summary("home_assistant_timer", "ok", start_time)
        _audit("home_assistant_timer", {"result": "ok", "action": action, "entity_id": entity_id})
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    service_map = {
        "start": "start",
        "pause": "pause",
        "cancel": "cancel",
        "finish": "finish",
    }
    service_data: dict[str, Any] = {"entity_id": entity_id}
    if action == "start":
        duration_text = str(args.get("duration", "")).strip()
        if duration_text:
            duration_seconds = _duration_seconds(duration_text)
            if duration_seconds is not None:
                total = max(1, int(round(duration_seconds)))
                hours, rem = divmod(total, 3600)
                minutes, seconds = divmod(rem, 60)
                service_data["duration"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            elif re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", duration_text):
                service_data["duration"] = duration_text
            else:
                _record_service_error("home_assistant_timer", start_time, "invalid_data")
                _audit("home_assistant_timer", {"result": "invalid_data", "field": "duration"})
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "duration must be HH:MM:SS or a relative duration like 5m.",
                        }
                    ]
                }
    with _recovery_operation(
        "home_assistant_timer",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("timer", service_map[action], service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant timer entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        recovery.mark_completed(detail="ok", context={"duration": service_data.get("duration")})
        record_summary("home_assistant_timer", "ok", start_time)
        _audit(
            "home_assistant_timer",
            {"result": "ok", "action": action, "entity_id": entity_id, "duration": service_data.get("duration")},
        )
        return {"content": [{"type": "text", "text": f"Home Assistant timer action executed: {action} on {entity_id}."}]}


async def home_assistant_area_entities(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_area_entities"):
        record_summary("home_assistant_area_entities", "denied", start_time, "policy")
        _audit("home_assistant_area_entities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_area_entities", start_time, "missing_config")
        _audit("home_assistant_area_entities", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    area = str(args.get("area", "")).strip()
    if not area:
        _record_service_error("home_assistant_area_entities", start_time, "missing_fields")
        _audit("home_assistant_area_entities", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "area is required."}]}
    domain_filter = str(args.get("domain", "")).strip().lower()
    include_states = _as_bool(args.get("include_states"), default=False)

    template = f"{{{{ area_entities({json.dumps(area)}) | join('\\n') }}}}"
    rendered, error_code = await _ha_render_template(template)
    if error_code is not None:
        _record_service_error("home_assistant_area_entities", start_time, error_code)
        _audit("home_assistant_area_entities", {"result": error_code, "area": area})
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Home Assistant template endpoint not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup was cancelled."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant area lookup endpoint."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant area lookup error."}]}

    raw_entities = [line.strip().lower() for line in (rendered or "").splitlines() if line.strip()]
    entities = sorted(set(raw_entities))
    if domain_filter:
        entities = [entity for entity in entities if entity.startswith(f"{domain_filter}.")]
    if not entities:
        record_summary("home_assistant_area_entities", "empty", start_time)
        _audit(
            "home_assistant_area_entities",
            {"result": "empty", "area": area, "domain": domain_filter},
        )
        return {"content": [{"type": "text", "text": "No entities found for that area filter."}]}

    payload: dict[str, Any] = {"area": area, "domain": domain_filter or None, "entities": entities}
    if include_states:
        states: list[dict[str, Any]] = []
        for entity_id in entities[:100]:
            entity_state, state_error = await _ha_get_state(entity_id)
            if state_error is not None:
                continue
            state_payload = entity_state or {}
            attributes = state_payload.get("attributes")
            friendly_name = ""
            if isinstance(attributes, dict):
                friendly_name = str(attributes.get("friendly_name", "")).strip()
            states.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "state": state_payload.get("state", "unknown"),
                }
            )
        payload["states"] = states
    record_summary("home_assistant_area_entities", "ok", start_time)
    _audit(
        "home_assistant_area_entities",
        {
            "result": "ok",
            "area": area,
            "domain": domain_filter,
            "count": len(entities),
            "include_states": include_states,
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


async def media_control(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("media_control"):
        record_summary("media_control", "denied", start_time, "policy")
        _audit("media_control", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("media_control", start_time, "missing_config")
        _audit("media_control", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    entity_id = str(args.get("entity_id", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()
    if not entity_id.startswith("media_player."):
        _record_service_error("media_control", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "entity_id must be a media_player entity."}]}
    action_map = {
        "play": ("media_play", {}),
        "pause": ("media_pause", {}),
        "turn_on": ("turn_on", {}),
        "turn_off": ("turn_off", {}),
        "toggle": ("toggle", {}),
        "mute": ("volume_mute", {"is_volume_muted": True}),
        "unmute": ("volume_mute", {"is_volume_muted": False}),
        "volume_set": ("volume_set", {}),
    }
    if action not in action_map:
        _record_service_error("media_control", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "action must be one of: play, pause, turn_on, turn_off, toggle, mute, unmute, volume_set.",
                }
            ]
        }
    service, data = action_map[action]
    payload_data = dict(data)
    if action == "volume_set":
        volume = _as_float(args.get("volume"), float("nan"))
        if not math.isfinite(volume) or volume < 0.0 or volume > 1.0:
            _record_service_error("media_control", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "volume must be a number between 0.0 and 1.0 for volume_set."}]}
        payload_data["volume_level"] = volume
    dry_run = _as_bool(args.get("dry_run"), default=False)
    safe_mode_forced = _safe_mode_enabled and not dry_run
    if safe_mode_forced:
        dry_run = True
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "media_control",
        args,
        mutating=not dry_run,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("media_control", start_time, "policy")
        _audit(
            "media_control",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "entity_id": entity_id, "action": action},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if not dry_run:
        preview = _preview_gate(
            tool_name="media_control",
            args=args,
            risk="medium",
            summary=f"media_control {action} on {entity_id}",
            signature_payload={"entity_id": entity_id, "action": action, "payload_data": payload_data},
            enforce_default=_plan_preview_require_ack,
        )
        if preview:
            record_summary("media_control", "dry_run", start_time, effect="plan_preview", risk="medium")
            _audit(
                "media_control",
                _identity_enriched_audit(
                    {"result": "preview_required", "entity_id": entity_id, "action": action},
                    identity_context,
                    [*identity_chain, "decision:preview_required"],
                ),
            )
            return {"content": [{"type": "text", "text": preview}]}
    if dry_run:
        record_summary("media_control", "dry_run", start_time)
        _audit(
            "media_control",
            _identity_enriched_audit(
                {
                    "result": "dry_run",
                    "entity_id": entity_id,
                    "action": action,
                    "data": payload_data,
                    "safe_mode_forced": safe_mode_forced,
                },
                identity_context,
                [*identity_chain, "decision:dry_run"],
            ),
        )
        text = f"DRY RUN: media_player.{service} on {entity_id} with {payload_data}"
        if safe_mode_forced:
            text = f"{text}. Safe mode forced dry-run."
        return {"content": [{"type": "text", "text": text}]}
    service_data = {"entity_id": entity_id, **payload_data}
    with _recovery_operation(
        "media_control",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("media_player", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("media_control", start_time, error_code)
            _audit("media_control", {"result": error_code, "entity_id": entity_id, "action": action})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Media player entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Media control request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Media control request was cancelled."}]}
            if error_code == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant media endpoint."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant media control error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("media_control", "ok", start_time, effect=f"{service} {entity_id}", risk="low")
        _audit(
            "media_control",
            _identity_enriched_audit(
                {"result": "ok", "entity_id": entity_id, "action": action},
                identity_context,
                [*identity_chain, "decision:execute"],
            ),
        )
        return {"content": [{"type": "text", "text": f"Media action executed: {action} on {entity_id}."}]}


async def weather_lookup(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("weather_lookup"):
        record_summary("weather_lookup", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("weather")
    if circuit_open:
        _record_service_error("weather_lookup", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("weather", circuit_remaining)}]}
    location = str(args.get("location", "")).strip()
    if not location:
        _record_service_error("weather_lookup", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "location is required."}]}
    units = str(args.get("units", _weather_units)).strip().lower() or _weather_units
    if units not in {"metric", "imperial"}:
        _record_service_error("weather_lookup", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "units must be metric or imperial."}]}
    geocode_params = {
        "name": location,
        "count": "1",
        "language": "en",
        "format": "json",
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_weather_timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://geocoding-api.open-meteo.com/v1/search", params=geocode_params) as resp:
                if resp.status != 200:
                    _record_service_error("weather_lookup", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Weather geocoding error ({resp.status})."}]}
                geocode = await resp.json()
            if not isinstance(geocode, dict):
                _record_service_error("weather_lookup", start_time, "invalid_json")
                return {"content": [{"type": "text", "text": "Invalid weather geocoding response."}]}
            results = geocode.get("results")
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                record_summary("weather_lookup", "empty", start_time)
                return {"content": [{"type": "text", "text": f"No weather match found for '{location}'."}]}
            place = results[0]
            latitude = place.get("latitude")
            longitude = place.get("longitude")
            if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                _record_service_error("weather_lookup", start_time, "invalid_json")
                return {"content": [{"type": "text", "text": "Invalid weather geocoding response."}]}
            forecast_params = {
                "latitude": str(float(latitude)),
                "longitude": str(float(longitude)),
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
                "wind_speed_unit": "mph" if units == "imperial" else "kmh",
            }
            async with session.get("https://api.open-meteo.com/v1/forecast", params=forecast_params) as resp:
                if resp.status != 200:
                    _record_service_error("weather_lookup", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Weather forecast error ({resp.status})."}]}
                forecast = await resp.json()
    except asyncio.TimeoutError:
        _record_service_error("weather_lookup", start_time, "timeout")
        return {"content": [{"type": "text", "text": "Weather request timed out."}]}
    except asyncio.CancelledError:
        _record_service_error("weather_lookup", start_time, "cancelled")
        return {"content": [{"type": "text", "text": "Weather request was cancelled."}]}
    except aiohttp.ClientError:
        _record_service_error("weather_lookup", start_time, "network_client_error")
        return {"content": [{"type": "text", "text": "Failed to reach weather provider."}]}
    except Exception:
        _record_service_error("weather_lookup", start_time, "unexpected")
        log.exception("Unexpected weather_lookup failure")
        return {"content": [{"type": "text", "text": "Unexpected weather lookup error."}]}

    if not isinstance(forecast, dict):
        _record_service_error("weather_lookup", start_time, "invalid_json")
        return {"content": [{"type": "text", "text": "Invalid weather forecast response."}]}
    current = forecast.get("current")
    if not isinstance(current, dict):
        _record_service_error("weather_lookup", start_time, "invalid_json")
        return {"content": [{"type": "text", "text": "Invalid weather forecast response."}]}
    temperature = current.get("temperature_2m")
    apparent = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    code = _as_exact_int(current.get("weather_code"))
    code_map = {
        0: "clear",
        1: "mostly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "fog",
        51: "drizzle",
        53: "drizzle",
        55: "drizzle",
        61: "rain",
        63: "rain",
        65: "heavy rain",
        71: "snow",
        73: "snow",
        75: "heavy snow",
        95: "thunderstorm",
    }
    condition = code_map.get(code, "unknown conditions")
    place_name = str(place.get("name", location)).strip() or location
    country = str(place.get("country", "")).strip()
    place_label = f"{place_name}, {country}" if country else place_name
    temp_unit = "F" if units == "imperial" else "C"
    wind_unit = "mph" if units == "imperial" else "km/h"
    _integration_record_success("weather")
    record_summary("weather_lookup", "ok", start_time)
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"{place_label}: {temperature}°{temp_unit}, feels like {apparent}°{temp_unit}, "
                    f"{condition}, humidity {humidity}%, wind {wind} {wind_unit}."
                ),
            }
        ]
    }


async def webhook_trigger(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    identity_probe = _identity_context(args)
    if not _tool_permitted("webhook_trigger"):
        record_summary("webhook_trigger", "denied", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "policy"},
                identity_probe,
                ["tool=webhook_trigger", "deny:tool_policy"],
            ),
        )
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("webhook")
    if circuit_open:
        _record_service_error("webhook_trigger", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("webhook", circuit_remaining)}]}
    url = str(args.get("url", "")).strip()
    if not url:
        _record_service_error("webhook_trigger", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "url is required."}]}
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "https_required"},
                identity_probe,
                ["tool=webhook_trigger", "deny:https_required"],
            ),
        )
        return {"content": [{"type": "text", "text": "Webhook URL must use https."}]}
    if not _webhook_host_allowed(url):
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "allowlist", "host": parsed.hostname or ""},
                identity_probe,
                ["tool=webhook_trigger", "deny:allowlist"],
            ),
        )
        return {"content": [{"type": "text", "text": "Webhook host is not in WEBHOOK_ALLOWLIST."}]}
    method = str(args.get("method", "POST")).strip().upper() or "POST"
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "method must be one of GET, POST, PUT, PATCH, DELETE."}]}
    payload = args.get("payload")
    if payload is not None and not isinstance(payload, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "payload must be an object when provided."}]}
    headers_raw = args.get("headers")
    if headers_raw is not None and not isinstance(headers_raw, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "headers must be an object when provided."}]}
    headers: dict[str, str] = {}
    for key, value in (headers_raw or {}).items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        headers[clean_key] = str(value)
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "webhook_trigger",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "method": method, "host": parsed.hostname or ""},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    preview = _preview_gate(
        tool_name="webhook_trigger",
        args=args,
        risk="high",
        summary=f"{method} {url}",
        signature_payload={"method": method, "url": url, "payload": payload or {}, "headers": headers},
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("webhook_trigger", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "preview_required", "method": method, "host": parsed.hostname or ""},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}
    if _webhook_auth_token and not any(key.lower() == "authorization" for key in headers):
        headers["Authorization"] = f"Bearer {_webhook_auth_token}"
    timeout_sec = _as_float(
        args.get("timeout_sec", _webhook_timeout_sec),
        _webhook_timeout_sec,
        minimum=0.1,
        maximum=30.0,
    )
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec, minimum=0.1, maximum=30.0))
    request_kwargs: dict[str, Any] = {"headers": headers or None}
    if method in {"POST", "PUT", "PATCH"}:
        request_kwargs["json"] = payload or {}
    with _recovery_operation(
        "webhook_trigger",
        operation=f"{method} {parsed.hostname or ''}",
        context={"method": method, "host": parsed.hostname or ""},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **request_kwargs) as resp:
                    body = await resp.text()
                    if 200 <= resp.status < 300:
                        _integration_record_success("webhook")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("webhook_trigger", "ok", start_time)
                        _audit(
                            "webhook_trigger",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "method": method,
                                    "host": parsed.hostname or "",
                                    "status": resp.status,
                                    "response_length": len(body),
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        body_preview = body[:200]
                        suffix = f" body={body_preview}" if body_preview else ""
                        return {"content": [{"type": "text", "text": f"Webhook delivered ({resp.status}).{suffix}"}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("webhook_trigger", start_time, "auth")
                        _audit(
                            "webhook_trigger",
                            {"result": "auth", "method": method, "host": parsed.hostname or "", "status": resp.status},
                        )
                        return {"content": [{"type": "text", "text": "Webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("webhook_trigger", start_time, "http_error")
                    _audit(
                        "webhook_trigger",
                        {"result": "http_error", "method": method, "host": parsed.hostname or "", "status": resp.status},
                    )
                    return {"content": [{"type": "text", "text": f"Webhook request failed ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("webhook_trigger", start_time, "timeout")
            _audit("webhook_trigger", {"result": "timeout", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("webhook_trigger", start_time, "cancelled")
            _audit("webhook_trigger", {"result": "cancelled", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("webhook_trigger", start_time, "network_client_error")
            _audit("webhook_trigger", {"result": "network_client_error", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Failed to reach webhook endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("webhook_trigger", start_time, "unexpected")
            _audit("webhook_trigger", {"result": "unexpected", "method": method, "host": parsed.hostname or ""})
            log.exception("Unexpected webhook_trigger failure")
            return {"content": [{"type": "text", "text": "Unexpected webhook trigger error."}]}


async def webhook_inbound_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_list"):
        record_summary("webhook_inbound_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    rows = list(reversed(_inbound_webhook_events))[:limit]
    record_summary("webhook_inbound_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(rows, default=str)}]}


async def webhook_inbound_clear(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_clear"):
        record_summary("webhook_inbound_clear", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    count = len(_inbound_webhook_events)
    _inbound_webhook_events.clear()
    record_summary("webhook_inbound_clear", "ok", start_time)
    _audit("webhook_inbound_clear", {"result": "ok", "cleared_count": count})
    return {"content": [{"type": "text", "text": f"Cleared inbound webhook events: {count}."}]}


async def slack_notify(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("slack_notify"):
        record_summary("slack_notify", "denied", start_time, "policy")
        _audit("slack_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("channels")
    if circuit_open:
        _record_service_error("slack_notify", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("channels", circuit_remaining)}]}
    if not _slack_webhook_url:
        _record_service_error("slack_notify", start_time, "missing_config")
        _audit("slack_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Slack webhook not configured. Set SLACK_WEBHOOK_URL."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("slack_notify", start_time, "missing_fields")
        _audit("slack_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "message is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "slack_notify",
        args,
        mutating=True,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("slack_notify", start_time, "policy")
        _audit(
            "slack_notify",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_webhook_timeout_sec, minimum=0.1, maximum=30.0))
    with _recovery_operation("slack_notify", operation="send_slack", context={"message_length": len(message)}) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(_slack_webhook_url, json={"text": message}) as resp:
                    if 200 <= resp.status < 300:
                        _integration_record_success("channels")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("slack_notify", "ok", start_time)
                        _audit(
                            "slack_notify",
                            _identity_enriched_audit(
                                {"result": "ok", "message_length": len(message)},
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        return {"content": [{"type": "text", "text": "Slack notification sent."}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("slack_notify", start_time, "auth")
                        _audit("slack_notify", {"result": "auth", "status": resp.status})
                        return {"content": [{"type": "text", "text": "Slack webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("slack_notify", start_time, "http_error")
                    _audit("slack_notify", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Slack webhook error ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("slack_notify", start_time, "timeout")
            _audit("slack_notify", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Slack webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("slack_notify", start_time, "cancelled")
            _audit("slack_notify", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Slack webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("slack_notify", start_time, "network_client_error")
            _audit("slack_notify", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Slack webhook."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("slack_notify", start_time, "unexpected")
            _audit("slack_notify", {"result": "unexpected"})
            log.exception("Unexpected slack_notify failure")
            return {"content": [{"type": "text", "text": "Unexpected Slack webhook error."}]}


async def discord_notify(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("discord_notify"):
        record_summary("discord_notify", "denied", start_time, "policy")
        _audit("discord_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("channels")
    if circuit_open:
        _record_service_error("discord_notify", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("channels", circuit_remaining)}]}
    if not _discord_webhook_url:
        _record_service_error("discord_notify", start_time, "missing_config")
        _audit("discord_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Discord webhook not configured. Set DISCORD_WEBHOOK_URL."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("discord_notify", start_time, "missing_fields")
        _audit("discord_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "message is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "discord_notify",
        args,
        mutating=True,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("discord_notify", start_time, "policy")
        _audit(
            "discord_notify",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_webhook_timeout_sec, minimum=0.1, maximum=30.0))
    with _recovery_operation("discord_notify", operation="send_discord", context={"message_length": len(message)}) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(_discord_webhook_url, json={"content": message}) as resp:
                    if 200 <= resp.status < 300:
                        _integration_record_success("channels")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("discord_notify", "ok", start_time)
                        _audit(
                            "discord_notify",
                            _identity_enriched_audit(
                                {"result": "ok", "message_length": len(message)},
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        return {"content": [{"type": "text", "text": "Discord notification sent."}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("discord_notify", start_time, "auth")
                        _audit("discord_notify", {"result": "auth", "status": resp.status})
                        return {"content": [{"type": "text", "text": "Discord webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("discord_notify", start_time, "http_error")
                    _audit("discord_notify", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Discord webhook error ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("discord_notify", start_time, "timeout")
            _audit("discord_notify", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Discord webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("discord_notify", start_time, "cancelled")
            _audit("discord_notify", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Discord webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("discord_notify", start_time, "network_client_error")
            _audit("discord_notify", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Discord webhook."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("discord_notify", start_time, "unexpected")
            _audit("discord_notify", {"result": "unexpected"})
            log.exception("Unexpected discord_notify failure")
            return {"content": [{"type": "text", "text": "Unexpected Discord webhook error."}]}


def _record_email_history(recipient: str, subject: str) -> None:
    item = {
        "timestamp": time.time(),
        "to": recipient,
        "subject": subject,
    }
    _email_history.append(item)
    if len(_email_history) > 200:
        del _email_history[:-200]
    if _memory is not None:
        try:
            _memory.add_memory(
                f"Email sent to {recipient}: {subject}",
                kind="email_sent",
                tags=["integration", "email"],
                sensitivity=0.4,
                source="integration.email",
            )
        except Exception:
            log.warning("Failed to persist email send metadata", exc_info=True)


def _send_email_sync(*, recipient: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = _email_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(
        _email_smtp_host,
        _email_smtp_port,
        timeout=_effective_act_timeout(_email_timeout_sec),
    ) as smtp:
        smtp.ehlo()
        if _email_use_tls:
            smtp.starttls()
            smtp.ehlo()
        if _email_smtp_username:
            smtp.login(_email_smtp_username, _email_smtp_password)
        smtp.send_message(msg)


async def email_send(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("email_send"):
        record_summary("email_send", "denied", start_time, "policy")
        _audit("email_send", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("email")
    if circuit_open:
        _record_service_error("email_send", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("email", circuit_remaining)}]}
    if not _email_smtp_host or not _email_from or not _email_default_to:
        _record_service_error("email_send", start_time, "missing_config")
        _audit("email_send", {"result": "missing_config"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Email not configured. Set EMAIL_SMTP_HOST, EMAIL_FROM, and EMAIL_DEFAULT_TO.",
                }
            ]
        }
    subject = str(args.get("subject", "")).strip()
    body = str(args.get("body", "")).strip()
    if not subject or not body:
        _record_service_error("email_send", start_time, "missing_fields")
        _audit("email_send", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "subject and body are required."}]}
    confirm = _as_bool(args.get("confirm"), default=False)
    if not confirm:
        _record_service_error("email_send", start_time, "policy")
        _audit("email_send", {"result": "denied", "reason": "confirm_required"})
        return {"content": [{"type": "text", "text": "Set confirm=true to send email."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "email_send",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("email_send", start_time, "policy")
        _audit(
            "email_send",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    recipient = str(args.get("to", "")).strip() or _email_default_to
    preview = _preview_gate(
        tool_name="email_send",
        args=args,
        risk="high",
        summary=f"email_send to {recipient} subject='{subject[:80]}'",
        signature_payload={
            "to": recipient,
            "subject": subject,
            "body_length": len(body),
            "body_digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("email_send", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "email_send",
            _identity_enriched_audit(
                {"result": "preview_required", "to": recipient, "subject_length": len(subject)},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}
    with _recovery_operation(
        "email_send",
        operation=f"send:{recipient}",
        context={"to": recipient, "subject_length": len(subject)},
    ) as recovery:
        try:
            await asyncio.to_thread(_send_email_sync, recipient=recipient, subject=subject, body=body)
        except smtplib.SMTPAuthenticationError:
            recovery.mark_failed("auth")
            _record_service_error("email_send", start_time, "auth")
            _audit("email_send", {"result": "auth", "to": recipient})
            return {"content": [{"type": "text", "text": "Email SMTP authentication failed."}]}
        except (smtplib.SMTPException, OSError, TimeoutError):
            recovery.mark_failed("network_client_error")
            _record_service_error("email_send", start_time, "network_client_error")
            _audit("email_send", {"result": "network_client_error", "to": recipient})
            return {"content": [{"type": "text", "text": "Failed to reach SMTP server."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("email_send", start_time, "unexpected")
            _audit("email_send", {"result": "unexpected", "to": recipient})
            log.exception("Unexpected email_send failure")
            return {"content": [{"type": "text", "text": "Unexpected email send error."}]}
        _integration_record_success("email")
        _record_email_history(recipient, subject)
        recovery.mark_completed(detail="ok")
        record_summary("email_send", "ok", start_time)
        _audit(
            "email_send",
            _identity_enriched_audit(
                {"result": "ok", "to": recipient, "subject_length": len(subject), "body_length": len(body)},
                identity_context,
                [*identity_chain, "decision:execute"],
            ),
        )
        return {"content": [{"type": "text", "text": f"Email sent to {recipient}."}]}


async def email_summary(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("email_summary"):
        record_summary("email_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    lines: list[str] = []
    if _memory is not None:
        try:
            rows = _memory.recent(limit=limit, kind="email_sent", sources=["integration.email"])
        except Exception:
            rows = []
        for entry in rows:
            lines.append(f"- {entry.text}")
    else:
        for item in list(reversed(_email_history))[:limit]:
            ts = float(item.get("timestamp", 0.0))
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            recipient = str(item.get("to", ""))
            subject = str(item.get("subject", ""))
            lines.append(f"- {when} | to={recipient} | subject={subject}")
    if not lines:
        record_summary("email_summary", "empty", start_time)
        return {"content": [{"type": "text", "text": "No email history found."}]}
    record_summary("email_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _list_reminder_payloads(*, include_completed: bool, limit: int, now_ts: float) -> list[dict[str, Any]]:
    if _memory is not None:
        pending_rows = _memory.list_reminders(status="pending", now=now_ts, limit=limit)
        completed_rows = _memory.list_reminders(status="completed", limit=limit) if include_completed else []
        payloads = [
            {
                "id": int(row.id),
                "text": str(row.text),
                "due_at": float(row.due_at),
                "created_at": float(row.created_at),
                "status": str(row.status),
                "completed_at": float(row.completed_at) if row.completed_at is not None else None,
                "notified_at": float(row.notified_at) if row.notified_at is not None else None,
            }
            for row in [*pending_rows, *completed_rows]
        ]
    else:
        payloads = list(_reminders.values())
        if not include_completed:
            payloads = [payload for payload in payloads if str(payload.get("status", "pending")) == "pending"]
    payloads = sorted(payloads, key=lambda payload: float(payload.get("due_at", now_ts)))
    return payloads[:limit]


def _due_unnotified_reminder_payloads(*, limit: int, now_ts: float) -> list[dict[str, Any]]:
    if _memory is not None:
        rows = _memory.list_reminders(
            status="pending",
            due_only=True,
            include_notified=False,
            now=now_ts,
            limit=limit,
        )
        return [
            {
                "id": int(row.id),
                "text": str(row.text),
                "due_at": float(row.due_at),
                "created_at": float(row.created_at),
                "status": str(row.status),
                "completed_at": float(row.completed_at) if row.completed_at is not None else None,
                "notified_at": float(row.notified_at) if row.notified_at is not None else None,
            }
            for row in rows
        ]
    rows = [
        payload
        for payload in _reminders.values()
        if str(payload.get("status", "pending")) == "pending"
        and float(payload.get("due_at", now_ts + 1.0)) <= now_ts
        and payload.get("notified_at") is None
    ]
    rows = sorted(rows, key=lambda payload: float(payload.get("due_at", now_ts)))
    return rows[:limit]


async def reminder_create(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("reminder_create"):
        record_summary("reminder_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("reminder_create", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Reminder text is required."}]}
    now = time.time()
    due_at = _parse_due_timestamp(args.get("due"), now_ts=now)
    if due_at is None:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Reminder due value must be epoch seconds, ISO datetime, or a relative duration like 'in 20m'.",
                }
            ]
        }
    if due_at <= now:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Reminder due time must be in the future."}]}
    pending_count = int(_reminder_status().get("pending_count", 0))
    if pending_count >= REMINDER_MAX_ACTIVE:
        _record_service_error("reminder_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Too many pending reminders ({REMINDER_MAX_ACTIVE} max)."}]}

    reminder_id: int
    if _memory is not None:
        try:
            reminder_id = _memory.add_reminder(text=text, due_at=due_at, created_at=now)
        except Exception:
            _record_service_error("reminder_create", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Reminder create failed: persistent storage unavailable."}]}
    else:
        reminder_id = _allocate_reminder_id()
    _reminders[reminder_id] = {
        "id": reminder_id,
        "text": text,
        "due_at": due_at,
        "created_at": now,
        "status": "pending",
        "completed_at": None,
        "notified_at": None,
    }
    due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_at))
    record_summary("reminder_create", "ok", start_time, effect=f"reminder_id={reminder_id}", risk="low")
    _audit(
        "reminder_create",
        {
            "result": "ok",
            "reminder_id": reminder_id,
            "text_length": len(text),
            "due_at": due_at,
        },
    )
    return {"content": [{"type": "text", "text": f"Reminder {reminder_id} set for {due_local}."}]}


async def reminder_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("reminder_list"):
        record_summary("reminder_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    include_completed = _as_bool(args.get("include_completed"), default=False)
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=100)
    now = time.time()
    try:
        payloads = _list_reminder_payloads(include_completed=include_completed, limit=limit, now_ts=now)
    except Exception:
        _record_service_error("reminder_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": "Reminder list failed: persistent storage unavailable."}]}
    if not payloads:
        record_summary("reminder_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No reminders found."}]}
    lines: list[str] = []
    for payload in payloads:
        reminder_id = int(payload.get("id", 0))
        text = str(payload.get("text", "")).strip() or "(untitled)"
        status = str(payload.get("status", "pending"))
        due_at = float(payload.get("due_at", now))
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_at))
        if status == "completed":
            completed_at = payload.get("completed_at")
            completed_local = (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(completed_at)))
                if completed_at is not None
                else "unknown"
            )
            lines.append(f"- {reminder_id}: {text} (completed at {completed_local}; due at {due_local})")
            continue
        remaining = due_at - now
        if remaining <= 0.0:
            when_text = f"overdue by {_format_duration(abs(remaining))}"
        else:
            when_text = f"due in {_format_duration(remaining)}"
        lines.append(f"- {reminder_id}: {text} ({when_text}; at {due_local})")
    record_summary("reminder_list", "ok", start_time)
    _audit(
        "reminder_list",
        {"result": "ok", "count": len(lines), "include_completed": include_completed},
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def reminder_complete(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("reminder_complete"):
        record_summary("reminder_complete", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    reminder_id = _as_exact_int(args.get("reminder_id"))
    if reminder_id is None or reminder_id <= 0:
        _record_service_error("reminder_complete", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "reminder_id must be a positive integer."}]}
    if _memory is not None:
        try:
            completed = _memory.complete_reminder(reminder_id)
        except Exception:
            _record_service_error("reminder_complete", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Reminder complete failed: persistent storage unavailable."}]}
        if not completed:
            _record_service_error("reminder_complete", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Reminder not found."}]}
    else:
        payload = _reminders.get(reminder_id)
        if payload is None or str(payload.get("status", "pending")) != "pending":
            _record_service_error("reminder_complete", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Reminder not found."}]}
        payload["status"] = "completed"
        payload["completed_at"] = time.time()
    if reminder_id in _reminders:
        _reminders[reminder_id]["status"] = "completed"
        _reminders[reminder_id]["completed_at"] = time.time()
    record_summary("reminder_complete", "ok", start_time, effect=f"reminder_id={reminder_id}", risk="low")
    _audit("reminder_complete", {"result": "ok", "reminder_id": reminder_id})
    return {"content": [{"type": "text", "text": f"Completed reminder {reminder_id}."}]}


async def reminder_notify_due(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("reminder_notify_due"):
        record_summary("reminder_notify_due", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _tool_permitted("pushover_notify"):
        _record_service_error("reminder_notify_due", start_time, "policy")
        _audit("reminder_notify_due", {"result": "denied", "reason": "pushover_policy"})
        return {"content": [{"type": "text", "text": "Pushover notifications are disabled by policy."}]}
    if not _config or not str(_config.pushover_api_token).strip() or not str(_config.pushover_user_key).strip():
        _record_service_error("reminder_notify_due", start_time, "missing_config")
        _audit("reminder_notify_due", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    title = str(args.get("title", "Jarvis reminders")).strip() or "Jarvis reminders"
    now = time.time()
    try:
        due_payloads = _due_unnotified_reminder_payloads(limit=limit, now_ts=now)
    except Exception:
        _record_service_error("reminder_notify_due", start_time, "storage_error")
        return {
            "content": [
                {"type": "text", "text": "Reminder notification dispatch failed: persistent storage unavailable."}
            ]
        }
    if not due_payloads:
        record_summary("reminder_notify_due", "empty", start_time)
        _audit("reminder_notify_due", {"result": "empty", "limit": limit})
        return {"content": [{"type": "text", "text": "No due reminders awaiting notification."}]}

    policy = _normalize_nudge_policy(args.get("nudge_policy", _nudge_policy))
    quiet_active = _quiet_window_active(now_ts=now)
    deferred_count = 0
    dispatch_payloads = due_payloads
    if quiet_active and policy in {"defer", "adaptive"}:
        if policy == "defer":
            deferred_count = len(dispatch_payloads)
            dispatch_payloads = []
        else:
            urgent_overdue_sec = _as_float(args.get("urgent_overdue_sec", 3600.0), 3600.0, minimum=60.0, maximum=86_400.0)
            urgent_payloads: list[dict[str, Any]] = []
            for payload in dispatch_payloads:
                due_at = float(payload.get("due_at", now))
                overdue_sec = max(0.0, now - due_at)
                if overdue_sec >= urgent_overdue_sec:
                    urgent_payloads.append(payload)
            deferred_count = max(0, len(dispatch_payloads) - len(urgent_payloads))
            dispatch_payloads = urgent_payloads
    if not dispatch_payloads and deferred_count > 0:
        record_summary("reminder_notify_due", "deferred", start_time, effect=f"deferred={deferred_count}", risk="low")
        _audit(
            "reminder_notify_due",
            {
                "result": "deferred",
                "policy": policy,
                "quiet_window_active": quiet_active,
                "deferred_count": deferred_count,
                "limit": limit,
            },
        )
        return {"content": [{"type": "text", "text": f"Deferred {deferred_count} due reminder notifications until quiet hours end."}]}

    sent = 0
    failed = 0
    for payload in dispatch_payloads:
        reminder_id = int(payload.get("id", 0))
        text = str(payload.get("text", "")).strip() or "(untitled)"
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(payload.get("due_at", now))))
        notify_result = await pushover_notify(
            {"title": title, "priority": 0, "message": f"Reminder {reminder_id}: {text} (due {due_local})"}
        )
        notify_text = str(notify_result.get("content", [{}])[0].get("text", "")).strip().lower()
        if "notification sent" not in notify_text:
            failed += 1
            continue
        sent += 1
        if _memory is not None:
            try:
                _memory.mark_reminder_notified(reminder_id, notified_at=time.time())
            except Exception:
                failed += 1
                sent -= 1
                continue
        if reminder_id in _reminders:
            _reminders[reminder_id]["notified_at"] = time.time()
    if sent == 0 and failed > 0:
        _record_service_error("reminder_notify_due", start_time, "api_error")
        _audit(
            "reminder_notify_due",
            {
                "result": "api_error",
                "sent": sent,
                "failed": failed,
                "deferred_count": deferred_count,
                "policy": policy,
                "quiet_window_active": quiet_active,
            },
        )
        return {"content": [{"type": "text", "text": "Unable to send due reminder notifications."}]}
    record_summary("reminder_notify_due", "ok", start_time, effect=f"sent={sent}", risk="low")
    _audit(
        "reminder_notify_due",
        {
            "result": "ok",
            "sent": sent,
            "failed": failed,
            "deferred_count": deferred_count,
            "policy": policy,
            "quiet_window_active": quiet_active,
        },
    )
    suffix = f" ({failed} failed)." if failed else "."
    if deferred_count > 0:
        suffix += f" Deferred: {deferred_count}."
    return {"content": [{"type": "text", "text": f"Due reminder notifications sent: {sent}{suffix}"}]}


async def _calendar_fetch_events(
    *,
    calendar_entity_id: str | None,
    start_ts: float,
    end_ts: float,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    params = {"start": _timestamp_to_iso_utc(start_ts), "end": _timestamp_to_iso_utc(end_ts)}
    entity_ids: list[str]
    if calendar_entity_id:
        entity_ids = [calendar_entity_id]
    else:
        calendars_payload, calendars_error = await _ha_get_json("/api/calendars")
        if calendars_error is not None:
            return None, calendars_error
        if not isinstance(calendars_payload, list):
            return None, "invalid_json"
        entity_ids = []
        for item in calendars_payload:
            if not isinstance(item, dict):
                continue
            entity = str(item.get("entity_id", "")).strip().lower()
            if entity:
                entity_ids.append(entity)
        if not entity_ids:
            return [], None
    events: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        payload, error_code = await _ha_get_json(f"/api/calendars/{entity_id}", params=params)
        if error_code is not None:
            return None, error_code
        if not isinstance(payload, list):
            return None, "invalid_json"
        for item in payload:
            if not isinstance(item, dict):
                continue
            start_raw = item.get("start")
            start_event = _parse_calendar_event_timestamp(start_raw)
            if start_event is None:
                continue
            end_event = _parse_calendar_event_timestamp(item.get("end"))
            all_day = isinstance(start_raw, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_raw.strip()))
            events.append(
                {
                    "entity_id": entity_id,
                    "summary": str(item.get("summary", "")).strip() or "(untitled)",
                    "location": str(item.get("location", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                    "start": start_raw,
                    "end": item.get("end"),
                    "start_ts": start_event,
                    "end_ts": end_event,
                    "all_day": all_day,
                }
            )
    events.sort(key=lambda event: float(event.get("start_ts", start_ts)))
    return events, None


def _parse_calendar_window(args: dict[str, Any]) -> tuple[float | None, float | None]:
    now = time.time()
    start_raw = str(args.get("start", "")).strip()
    end_raw = str(args.get("end", "")).strip()
    start_ts = now
    if start_raw:
        parsed_start = _parse_due_timestamp(start_raw, now_ts=now)
        if parsed_start is None:
            return None, None
        start_ts = parsed_start
    if end_raw:
        end_ts = _parse_due_timestamp(end_raw, now_ts=now)
        if end_ts is None:
            return None, None
    else:
        window_hours = _as_float(
            args.get("window_hours", CALENDAR_DEFAULT_WINDOW_HOURS),
            CALENDAR_DEFAULT_WINDOW_HOURS,
            minimum=0.1,
            maximum=CALENDAR_MAX_WINDOW_HOURS,
        )
        end_ts = start_ts + (window_hours * 3600.0)
    if end_ts <= start_ts:
        return None, None
    return start_ts, end_ts


async def calendar_events(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("calendar_events"):
        record_summary("calendar_events", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("calendar_events", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    start_ts, end_ts = _parse_calendar_window(args)
    if start_ts is None or end_ts is None:
        _record_service_error("calendar_events", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid calendar window. Use valid ISO timestamps or relative durations for start/end.",
                }
            ]
        }
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=100)
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower() or None
    events, error_code = await _calendar_fetch_events(
        calendar_entity_id=calendar_entity_id,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    if error_code is not None:
        _record_service_error("calendar_events", start_time, error_code)
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Calendar endpoint or entity not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Calendar request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Calendar request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant calendar endpoint."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant calendar response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant calendar error."}]}
    rows = (events or [])[:limit]
    if not rows:
        record_summary("calendar_events", "empty", start_time)
        return {"content": [{"type": "text", "text": "No calendar events found in the selected window."}]}
    lines: list[str] = []
    for event in rows:
        start_value = float(event.get("start_ts", start_ts))
        if bool(event.get("all_day")):
            when = time.strftime("%Y-%m-%d", time.localtime(start_value)) + " (all day)"
        else:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_value))
        summary = str(event.get("summary", "(untitled)"))
        entity = str(event.get("entity_id", "calendar"))
        location = str(event.get("location", "")).strip()
        location_text = f" @ {location}" if location else ""
        lines.append(f"- {when} | {summary} [{entity}]{location_text}")
    record_summary("calendar_events", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def calendar_next_event(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("calendar_next_event"):
        record_summary("calendar_next_event", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("calendar_next_event", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    window_hours = _as_float(
        args.get("window_hours", CALENDAR_DEFAULT_WINDOW_HOURS),
        CALENDAR_DEFAULT_WINDOW_HOURS,
        minimum=0.1,
        maximum=CALENDAR_MAX_WINDOW_HOURS,
    )
    now = time.time()
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower() or None
    events, error_code = await _calendar_fetch_events(
        calendar_entity_id=calendar_entity_id,
        start_ts=now,
        end_ts=now + (window_hours * 3600.0),
    )
    if error_code is not None:
        _record_service_error("calendar_next_event", start_time, error_code)
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Calendar endpoint or entity not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Calendar request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Calendar request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant calendar endpoint."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant calendar response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant calendar error."}]}
    if not events:
        record_summary("calendar_next_event", "empty", start_time)
        return {"content": [{"type": "text", "text": "No upcoming calendar events found."}]}
    event = events[0]
    start_value = float(event.get("start_ts", now))
    if bool(event.get("all_day")):
        when = time.strftime("%Y-%m-%d", time.localtime(start_value)) + " (all day)"
    else:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_value))
    summary = str(event.get("summary", "(untitled)"))
    entity = str(event.get("entity_id", "calendar"))
    location = str(event.get("location", "")).strip()
    location_text = f" at {location}" if location else ""
    record_summary("calendar_next_event", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Next event: {summary} on {when}{location_text} [{entity}]."}]}


async def todoist_add_task(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("todoist_add_task"):
        record_summary("todoist_add_task", "denied", start_time, "policy")
        _audit("todoist_add_task", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("todoist")
    if circuit_open:
        _record_service_error("todoist_add_task", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("todoist", circuit_remaining)}]}
    if not _config or not str(_config.todoist_api_token).strip():
        _record_service_error("todoist_add_task", start_time, "missing_config")
        _audit("todoist_add_task", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Todoist not configured. Set TODOIST_API_TOKEN."}]}
    content = str(args.get("content", "")).strip()
    if not content:
        _record_service_error("todoist_add_task", start_time, "missing_fields")
        _audit("todoist_add_task", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Task content required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "todoist_add_task",
        args,
        mutating=True,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("todoist_add_task", start_time, "policy")
        _audit(
            "todoist_add_task",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    payload: dict[str, Any] = {"content": content}
    description = str(args.get("description", "")).strip()
    if description:
        payload["description"] = description
    due_string = str(args.get("due_string", "")).strip()
    if due_string:
        payload["due_string"] = due_string
    priority_raw = args.get("priority", 1)
    priority = _as_exact_int(priority_raw)
    if priority is None or priority < 1 or priority > 4:
        _record_service_error("todoist_add_task", start_time, "invalid_data")
        _audit("todoist_add_task", {"result": "invalid_data", "field": "priority"})
        return {"content": [{"type": "text", "text": "Todoist priority must be an integer between 1 and 4."}]}
    payload["priority"] = priority
    labels_raw = args.get("labels")
    if labels_raw is not None:
        if not isinstance(labels_raw, list):
            _record_service_error("todoist_add_task", start_time, "invalid_data")
            _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
            return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
        labels: list[str] = []
        for item in labels_raw:
            if not isinstance(item, str):
                _record_service_error("todoist_add_task", start_time, "invalid_data")
                _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
                return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
            cleaned = item.strip()
            if not cleaned:
                _record_service_error("todoist_add_task", start_time, "invalid_data")
                _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
                return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
            labels.append(cleaned)
        if labels:
            payload["labels"] = labels
    if str(getattr(_config, "todoist_project_id", "")).strip():
        payload["project_id"] = str(_config.todoist_project_id).strip()

    headers = {
        "Authorization": f"Bearer {str(_config.todoist_api_token).strip()}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_todoist_timeout_sec))
    with _recovery_operation("todoist_add_task", operation="create_task", context={"content_length": len(content)}) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post("https://api.todoist.com/rest/v2/tasks", headers=headers, json=payload) as resp:
                    if resp.status in {200, 201}:
                        try:
                            data = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("todoist_add_task", start_time, "invalid_json")
                            _audit("todoist_add_task", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response while creating task."}]}
                        if not isinstance(data, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("todoist_add_task", start_time, "invalid_json")
                            _audit("todoist_add_task", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response while creating task."}]}
                        task_id = data.get("id")
                        _integration_record_success("todoist")
                        recovery.mark_completed(detail="ok", context={"task_id": task_id})
                        record_summary("todoist_add_task", "ok", start_time)
                        _audit(
                            "todoist_add_task",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "task_id": task_id,
                                    "content_length": len(content),
                                    "project_id": payload.get("project_id", ""),
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        return {"content": [{"type": "text", "text": f"Todoist task created{f' (id={task_id})' if task_id else ''}."}]}
                    if resp.status == 401:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("todoist_add_task", start_time, "auth")
                        _audit("todoist_add_task", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Todoist authentication failed. Check TODOIST_API_TOKEN."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("todoist_add_task", start_time, "http_error")
                    _audit("todoist_add_task", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Todoist error ({resp.status}) creating task."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("todoist_add_task", start_time, "timeout")
            _audit("todoist_add_task", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Todoist request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("todoist_add_task", start_time, "cancelled")
            _audit("todoist_add_task", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Todoist request was cancelled."}]}
        except aiohttp.ClientError as e:
            recovery.mark_failed("network_client_error")
            _record_service_error("todoist_add_task", start_time, "network_client_error")
            _audit("todoist_add_task", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Todoist: {e}"}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("todoist_add_task", start_time, "unexpected")
            _audit("todoist_add_task", {"result": "unexpected"})
            log.exception("Unexpected todoist_add_task failure")
            return {"content": [{"type": "text", "text": "Unexpected Todoist error."}]}


async def todoist_list_tasks(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("todoist_list_tasks"):
        record_summary("todoist_list_tasks", "denied", start_time, "policy")
        _audit("todoist_list_tasks", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("todoist")
    if circuit_open:
        _record_service_error("todoist_list_tasks", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("todoist", circuit_remaining)}]}
    if not _config or not str(_config.todoist_api_token).strip():
        _record_service_error("todoist_list_tasks", start_time, "missing_config")
        _audit("todoist_list_tasks", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Todoist not configured. Set TODOIST_API_TOKEN."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    list_format = str(args.get("format", "short")).strip().lower() or "short"
    if list_format not in {"short", "verbose"}:
        _record_service_error("todoist_list_tasks", start_time, "invalid_data")
        _audit("todoist_list_tasks", {"result": "invalid_data", "field": "format"})
        return {"content": [{"type": "text", "text": "Todoist list format must be 'short' or 'verbose'."}]}
    headers = {"Authorization": f"Bearer {str(_config.todoist_api_token).strip()}"}
    params: dict[str, str] = {}
    if str(getattr(_config, "todoist_project_id", "")).strip():
        params["project_id"] = str(_config.todoist_project_id).strip()
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_todoist_timeout_sec))
    attempt = 0
    while True:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params or None) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        if not isinstance(data, list):
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        if any(not isinstance(item, dict) for item in data):
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        tasks = data[:limit]
                        _integration_record_success("todoist")
                        if not tasks:
                            record_summary("todoist_list_tasks", "empty", start_time)
                            _audit(
                                "todoist_list_tasks",
                                {
                                    "result": "empty",
                                    "limit": limit,
                                    "format": list_format,
                                    "project_id": params.get("project_id", ""),
                                },
                            )
                            return {"content": [{"type": "text", "text": "No Todoist tasks found."}]}

                        lines: list[str] = []
                        for task in tasks:
                            content = str(task.get("content", "")).strip() or "(untitled)"
                            if list_format == "short":
                                lines.append(f"- {content}")
                                continue
                            due_text = ""
                            due_payload = task.get("due")
                            if isinstance(due_payload, dict):
                                due_text = str(
                                    due_payload.get("string")
                                    or due_payload.get("date")
                                    or due_payload.get("datetime")
                                    or ""
                                ).strip()
                            labels = task.get("labels")
                            labels_text = ""
                            if isinstance(labels, list):
                                cleaned_labels = [str(item).strip() for item in labels if str(item).strip()]
                                if cleaned_labels:
                                    labels_text = ",".join(cleaned_labels)
                            meta: list[str] = []
                            if str(task.get("id", "")).strip():
                                meta.append(f"id={task['id']}")
                            if _as_exact_int(task.get("priority")) is not None:
                                meta.append(f"p={int(task['priority'])}")
                            if due_text:
                                meta.append(f"due={due_text}")
                            if labels_text:
                                meta.append(f"labels={labels_text}")
                            lines.append(f"- {content}" + (f" ({'; '.join(meta)})" if meta else ""))

                        record_summary("todoist_list_tasks", "ok", start_time)
                        _audit(
                            "todoist_list_tasks",
                            {
                                "result": "ok",
                                "count": len(tasks),
                                "limit": limit,
                                "format": list_format,
                                "project_id": params.get("project_id", ""),
                            },
                        )
                        return {"content": [{"type": "text", "text": "\n".join(lines)}]}
                    if resp.status == 401:
                        _record_service_error("todoist_list_tasks", start_time, "auth")
                        _audit("todoist_list_tasks", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Todoist authentication failed. Check TODOIST_API_TOKEN."}]}
                    _record_service_error("todoist_list_tasks", start_time, "http_error")
                    _audit("todoist_list_tasks", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Todoist error ({resp.status}) listing tasks."}]}
        except asyncio.TimeoutError:
            if attempt < TODOIST_LIST_MAX_RETRIES:
                await asyncio.sleep(_retry_backoff_delay(attempt))
                attempt += 1
                continue
            _record_service_error("todoist_list_tasks", start_time, "timeout")
            _audit("todoist_list_tasks", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Todoist request timed out."}]}
        except asyncio.CancelledError:
            _record_service_error("todoist_list_tasks", start_time, "cancelled")
            _audit("todoist_list_tasks", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Todoist request was cancelled."}]}
        except aiohttp.ClientError as e:
            if attempt < TODOIST_LIST_MAX_RETRIES:
                await asyncio.sleep(_retry_backoff_delay(attempt))
                attempt += 1
                continue
            _record_service_error("todoist_list_tasks", start_time, "network_client_error")
            _audit("todoist_list_tasks", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Todoist: {e}"}]}
        except Exception:
            _record_service_error("todoist_list_tasks", start_time, "unexpected")
            _audit("todoist_list_tasks", {"result": "unexpected"})
            log.exception("Unexpected todoist_list_tasks failure")
            return {"content": [{"type": "text", "text": "Unexpected Todoist error."}]}


async def pushover_notify(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("pushover_notify"):
        record_summary("pushover_notify", "denied", start_time, "policy")
        _audit("pushover_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("pushover")
    if circuit_open:
        _record_service_error("pushover_notify", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("pushover", circuit_remaining)}]}
    if not _config or not str(_config.pushover_api_token).strip() or not str(_config.pushover_user_key).strip():
        _record_service_error("pushover_notify", start_time, "missing_config")
        _audit("pushover_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("pushover_notify", start_time, "missing_fields")
        _audit("pushover_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Notification message required."}]}
    title = str(args.get("title", "Jarvis")).strip() or "Jarvis"
    priority_raw = args.get("priority", 0)
    priority = _as_exact_int(priority_raw)
    if priority is None or priority < -2 or priority > 2:
        _record_service_error("pushover_notify", start_time, "invalid_data")
        _audit("pushover_notify", {"result": "invalid_data", "field": "priority"})
        return {"content": [{"type": "text", "text": "Pushover priority must be an integer between -2 and 2."}]}
    payload = {
        "token": str(_config.pushover_api_token).strip(),
        "user": str(_config.pushover_user_key).strip(),
        "message": message,
        "title": title,
        "priority": priority,
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_pushover_timeout_sec))
    with _recovery_operation(
        "pushover_notify",
        operation="send_notification",
        context={"priority": priority, "message_length": len(message)},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post("https://api.pushover.net/1/messages.json", data=payload) as resp:
                    if resp.status == 200:
                        try:
                            body = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("pushover_notify", start_time, "invalid_json")
                            _audit("pushover_notify", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                        if not isinstance(body, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("pushover_notify", start_time, "invalid_json")
                            _audit("pushover_notify", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                        status_value = _as_exact_int(body.get("status"))
                        if status_value is None:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("pushover_notify", start_time, "invalid_json")
                            _audit("pushover_notify", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                        if status_value != 1:
                            errors = body.get("errors")
                            error_text = ""
                            if isinstance(errors, list):
                                error_text = "; ".join(str(item) for item in errors if str(item).strip())
                            recovery.mark_failed("api_error")
                            _record_service_error("pushover_notify", start_time, "api_error")
                            _audit("pushover_notify", {"result": "api_error", "error": error_text})
                            return {"content": [{"type": "text", "text": f"Pushover rejected notification{f': {error_text}' if error_text else '.'}"}]}
                        _integration_record_success("pushover")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("pushover_notify", "ok", start_time)
                        _audit(
                            "pushover_notify",
                            {
                                "result": "ok",
                                "title_length": len(title),
                                "priority": priority,
                                "message_length": len(message),
                            },
                        )
                        return {"content": [{"type": "text", "text": "Notification sent."}]}
                    if resp.status in {400, 401}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("pushover_notify", start_time, "auth")
                        _audit("pushover_notify", {"result": "auth", "status": resp.status})
                        return {"content": [{"type": "text", "text": "Pushover authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("pushover_notify", start_time, "http_error")
                    _audit("pushover_notify", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Pushover error ({resp.status}) sending notification."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("pushover_notify", start_time, "timeout")
            _audit("pushover_notify", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Pushover request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("pushover_notify", start_time, "cancelled")
            _audit("pushover_notify", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Pushover request was cancelled."}]}
        except aiohttp.ClientError as e:
            recovery.mark_failed("network_client_error")
            _record_service_error("pushover_notify", start_time, "network_client_error")
            _audit("pushover_notify", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Pushover: {e}"}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("pushover_notify", start_time, "unexpected")
            _audit("pushover_notify", {"result": "unexpected"})
            log.exception("Unexpected pushover_notify failure")
            return {"content": [{"type": "text", "text": "Unexpected Pushover error."}]}


async def skills_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("skills_list"):
        record_summary("skills_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    with suppress(Exception):
        _skill_registry.discover()
        set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(_skill_registry.status_snapshot(), default=str)}]}


async def skills_enable(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("skills_enable"):
        record_summary("skills_enable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_enable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_enable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.enable_skill(name)
    if not ok:
        _record_service_error("skills_enable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to enable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_enable", "ok", start_time)
    _audit("skills_enable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Enabled skill '{name}'."}]}


async def skills_disable(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("skills_disable"):
        record_summary("skills_disable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_disable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_disable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.disable_skill(name)
    if not ok:
        _record_service_error("skills_disable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to disable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_disable", "ok", start_time)
    _audit("skills_disable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Disabled skill '{name}'."}]}


async def skills_version(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("skills_version"):
        record_summary("skills_version", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_version", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_version", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    version = _skill_registry.skill_version(name)
    if version is None:
        _record_service_error("skills_version", start_time, "not_found")
        return {"content": [{"type": "text", "text": f"Skill '{name}' not found."}]}
    record_summary("skills_version", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps({"name": name, "version": version})}]}


async def get_time(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("get_time"):
        record_summary("get_time", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback
    tool_feedback("start")
    tool_feedback("done")
    record_summary("get_time", "ok", start_time)
    return {"content": [{"type": "text", "text": _now_local()}]}


async def system_status(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("system_status"):
        record_summary("system_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    memory_status = None
    if _memory is not None:
        try:
            memory_status = _memory.memory_status()
        except Exception as e:
            memory_status = {"error": str(e)}

    recent_tools: list[dict[str, object]] | dict[str, str]
    try:
        recent_tools = list_summaries(limit=5)
    except Exception as e:
        recent_tools = {"error": str(e)}
    identity_status = _identity_status_snapshot()
    tool_policy_status = {
        "allow_count": len(_tool_allowlist),
        "deny_count": len(_tool_denylist),
        "home_permission_profile": _home_permission_profile,
        "safe_mode_enabled": _safe_mode_enabled,
        "home_require_confirm_execute": bool(_home_require_confirm_execute),
        "home_conversation_enabled": bool(_home_conversation_enabled),
        "home_conversation_permission_profile": _home_conversation_permission_profile,
        "todoist_permission_profile": _todoist_permission_profile,
        "notification_permission_profile": _notification_permission_profile,
        "nudge_policy": _nudge_policy,
        "nudge_quiet_hours_start": _nudge_quiet_hours_start,
        "nudge_quiet_hours_end": _nudge_quiet_hours_end,
        "nudge_quiet_window_active": _quiet_window_active(),
        "email_permission_profile": _email_permission_profile,
        "memory_pii_guardrails_enabled": _memory_pii_guardrails_enabled,
        "identity_enforcement_enabled": _identity_enforcement_enabled,
        "identity_default_profile": _identity_default_profile,
        "identity_require_approval": _identity_require_approval,
        "plan_preview_require_ack": _plan_preview_require_ack,
    }
    observability_status = _observability_snapshot()
    integrations_status = _integration_health_snapshot()
    audit_status = _audit_status()
    health = _health_rollup(
        config_present=(_config is not None),
        memory_status=memory_status if isinstance(memory_status, dict) else None,
        recent_tools=recent_tools,
        identity_status=identity_status,
    )
    scorecard = _jarvis_scorecard_snapshot(
        recent_tools=recent_tools,
        health=health,
        observability=observability_status,
        identity=identity_status,
        tool_policy=tool_policy_status,
        audit=audit_status,
        integrations=integrations_status,
    )

    status = {
        "schema_version": SYSTEM_STATUS_CONTRACT_VERSION,
        "local_time": _now_local(),
        "home_assistant_configured": bool(_config and _config.has_home_assistant),
        "home_conversation_enabled": bool(_home_conversation_enabled),
        "todoist_configured": bool(_config and str(_config.todoist_api_token).strip()),
        "pushover_configured": bool(
            _config
            and str(_config.pushover_api_token).strip()
            and str(_config.pushover_user_key).strip()
        ),
        "motion_enabled": bool(_config and _config.motion_enabled),
        "home_tools_enabled": bool(_config and _config.home_enabled),
        "memory_enabled": bool(_config and _config.memory_enabled),
        "backchannel_style": _config.backchannel_style if _config else "unknown",
        "persona_style": _config.persona_style if _config else "unknown",
        "tool_policy": tool_policy_status,
        "timers": _timer_status(),
        "reminders": _reminder_status(),
        "voice_attention": _voice_attention_snapshot(),
        "turn_timeouts": {
            "watchdog_enabled": bool(_config and getattr(_config, "watchdog_enabled", False)),
            "listen_sec": _turn_timeout_listen_sec,
            "think_sec": _turn_timeout_think_sec,
            "speak_sec": _turn_timeout_speak_sec,
            "act_sec": _turn_timeout_act_sec,
        },
        "integrations": integrations_status,
        "identity": identity_status,
        "skills": _skills_status_snapshot(),
        "observability": observability_status,
        "scorecard": scorecard,
        "plan_preview": {
            "pending_count": len(_pending_plan_previews),
            "ttl_sec": PLAN_PREVIEW_TTL_SEC,
            "strict_mode": bool(_plan_preview_require_ack),
        },
        "retention_policy": {
            "memory_retention_days": _memory_retention_days,
            "audit_retention_days": _audit_retention_days,
        },
        "recovery_journal": _recovery_journal_status(limit=20),
        "memory": memory_status,
        "audit": audit_status,
        "recent_tools": recent_tools,
        "health": health,
    }
    record_summary("system_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status, default=str)}]}


async def system_status_contract(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("system_status_contract"):
        record_summary("system_status_contract", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    contract = {
        "schema_version": SYSTEM_STATUS_CONTRACT_VERSION,
        "top_level_required": [
            "schema_version",
            "local_time",
            "home_assistant_configured",
            "home_conversation_enabled",
            "todoist_configured",
            "pushover_configured",
            "motion_enabled",
            "home_tools_enabled",
            "memory_enabled",
            "backchannel_style",
            "persona_style",
            "tool_policy",
            "timers",
            "reminders",
            "voice_attention",
            "turn_timeouts",
            "integrations",
            "identity",
            "skills",
            "observability",
            "scorecard",
            "plan_preview",
            "retention_policy",
            "recovery_journal",
            "memory",
            "audit",
            "recent_tools",
            "health",
        ],
        "tool_policy_required": [
            "allow_count",
            "deny_count",
            "home_permission_profile",
            "safe_mode_enabled",
            "home_require_confirm_execute",
            "home_conversation_enabled",
            "home_conversation_permission_profile",
            "todoist_permission_profile",
            "notification_permission_profile",
            "nudge_policy",
            "nudge_quiet_hours_start",
            "nudge_quiet_hours_end",
            "nudge_quiet_window_active",
            "email_permission_profile",
            "memory_pii_guardrails_enabled",
            "identity_enforcement_enabled",
            "identity_default_profile",
            "identity_require_approval",
            "plan_preview_require_ack",
        ],
        "timers_required": [
            "active_count",
            "next_due_in_sec",
        ],
        "reminders_required": [
            "pending_count",
            "completed_count",
            "due_count",
            "next_due_in_sec",
        ],
        "voice_attention_required": [
            "mode",
            "followup_active",
            "sleeping",
            "active_room",
            "adaptive_silence_timeout_sec",
            "speech_rate_wps",
            "interruption_likelihood",
            "turn_choreography",
            "stt_diagnostics",
        ],
        "voice_attention_turn_choreography_required": [
            "phase",
            "label",
            "turn_lean",
            "turn_tilt",
            "turn_glance_yaw",
            "updated_at",
        ],
        "voice_attention_stt_diagnostics_required": [
            "source",
            "fallback_used",
            "confidence_score",
            "confidence_band",
            "avg_logprob",
            "avg_no_speech_prob",
            "language",
            "language_probability",
            "segment_count",
            "word_count",
            "char_count",
            "updated_at",
            "error",
        ],
        "turn_timeouts_required": [
            "watchdog_enabled",
            "listen_sec",
            "think_sec",
            "speak_sec",
            "act_sec",
        ],
        "integrations_required": [
            "home_assistant",
            "todoist",
            "pushover",
            "weather",
            "webhook",
            "email",
            "channels",
        ],
        "integration_circuit_breaker_required": [
            "open",
            "open_remaining_sec",
            "consecutive_failures",
            "opened_count",
            "cooldown_sec",
            "last_error",
            "last_failure_at",
            "last_success_at",
        ],
        "identity_required": [
            "enabled",
            "default_user",
            "default_profile",
            "require_approval",
            "approval_code_configured",
            "trusted_user_count",
            "trusted_users",
            "profile_count",
            "user_profiles",
        ],
        "skills_required": [
            "enabled",
            "loaded_count",
            "enabled_count",
            "skills",
        ],
        "observability_required": [
            "enabled",
            "uptime_sec",
            "restart_count",
            "intent_metrics",
            "alerts",
        ],
        "observability_intent_metrics_required": [
            "turn_count",
            "answer_intent_count",
            "action_intent_count",
            "hybrid_intent_count",
            "answer_sample_count",
            "completion_sample_count",
            "answer_quality_success_rate",
            "completion_success_rate",
            "correction_count",
            "correction_frequency",
        ],
        "scorecard_required": [
            "overall",
            "dimensions",
            "weights",
            "computed_at",
        ],
        "scorecard_overall_required": [
            "score",
            "grade",
        ],
        "scorecard_dimensions_required": [
            "latency",
            "reliability",
            "initiative",
            "trust",
        ],
        "scorecard_dimension_required": [
            "score",
            "grade",
        ],
        "plan_preview_required": [
            "pending_count",
            "ttl_sec",
            "strict_mode",
        ],
        "retention_policy_required": [
            "memory_retention_days",
            "audit_retention_days",
        ],
        "recovery_journal_required": [
            "path",
            "exists",
            "entry_count",
            "tracked_actions",
            "unresolved_count",
            "interrupted_count",
            "recent",
        ],
        "health_required": [
            "health_level",
            "reasons",
        ],
    }
    record_summary("system_status_contract", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(contract)}]}


async def jarvis_scorecard(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("jarvis_scorecard"):
        record_summary("jarvis_scorecard", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    memory_status: dict[str, Any] | None = None
    if _memory is not None:
        try:
            memory_status = _memory.memory_status()
        except Exception as exc:
            memory_status = {"error": str(exc)}

    try:
        recent_tools = list_summaries(limit=200)
    except Exception as exc:
        recent_tools = {"error": str(exc)}
    identity_status = _identity_status_snapshot()
    tool_policy_status = {
        "allow_count": len(_tool_allowlist),
        "deny_count": len(_tool_denylist),
        "home_permission_profile": _home_permission_profile,
        "safe_mode_enabled": _safe_mode_enabled,
        "home_require_confirm_execute": bool(_home_require_confirm_execute),
        "home_conversation_enabled": bool(_home_conversation_enabled),
        "home_conversation_permission_profile": _home_conversation_permission_profile,
        "todoist_permission_profile": _todoist_permission_profile,
        "notification_permission_profile": _notification_permission_profile,
        "nudge_policy": _nudge_policy,
        "nudge_quiet_hours_start": _nudge_quiet_hours_start,
        "nudge_quiet_hours_end": _nudge_quiet_hours_end,
        "nudge_quiet_window_active": _quiet_window_active(),
        "email_permission_profile": _email_permission_profile,
        "memory_pii_guardrails_enabled": _memory_pii_guardrails_enabled,
        "identity_enforcement_enabled": _identity_enforcement_enabled,
        "identity_default_profile": _identity_default_profile,
        "identity_require_approval": _identity_require_approval,
        "plan_preview_require_ack": _plan_preview_require_ack,
    }
    observability_status = _observability_snapshot()
    integrations_status = _integration_health_snapshot()
    audit_status = _audit_status()
    health = _health_rollup(
        config_present=(_config is not None),
        memory_status=memory_status if isinstance(memory_status, dict) else None,
        recent_tools=recent_tools,
        identity_status=identity_status,
    )
    scorecard = _jarvis_scorecard_snapshot(
        recent_tools=recent_tools,
        health=health,
        observability=observability_status,
        identity=identity_status,
        tool_policy=tool_policy_status,
        audit=audit_status,
        integrations=integrations_status,
    )
    record_summary("jarvis_scorecard", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(scorecard, default=str)}]}


# ── Memory + planning ───────────────────────────────────────

def _normalize_memory_scope(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in MEMORY_SCOPES:
        return text
    return None


def _memory_scope_tag(scope: str) -> str:
    return f"{MEMORY_SCOPE_TAG_PREFIX}{scope}"


def _memory_scope_from_tags(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        text = str(tag).strip().lower()
        if text.startswith(MEMORY_SCOPE_TAG_PREFIX):
            scope = text[len(MEMORY_SCOPE_TAG_PREFIX):]
            if scope in MEMORY_SCOPES:
                return scope
    return None


def _infer_memory_scope(*, kind: str, source: str) -> str:
    kind_text = str(kind or "").strip().lower()
    source_text = str(source or "").strip().lower()
    if kind_text in {"person", "contact", "people"}:
        return "people"
    if kind_text in {"project", "plan", "task", "task_plan"}:
        return "projects"
    if kind_text in {"rule", "household_rule", "policy"}:
        return "household_rules"
    if source_text in {"profile", "user"} or kind_text in {"profile", "preference"}:
        return "preferences"
    if source_text.startswith("integration.home") or source_text.startswith("integration.hass"):
        return "household_rules"
    return "preferences"


def _memory_scope_for_add(*, kind: str, source: str, tags: list[str], requested_scope: Any) -> str:
    explicit = _normalize_memory_scope(requested_scope)
    if explicit:
        return explicit
    tagged = _memory_scope_from_tags(tags)
    if tagged:
        return tagged
    return _infer_memory_scope(kind=kind, source=source)


def _memory_scope_tags(tags: list[str], scope: str) -> list[str]:
    cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
    filtered = [tag for tag in cleaned if not tag.lower().startswith(MEMORY_SCOPE_TAG_PREFIX)]
    filtered.append(_memory_scope_tag(scope))
    return filtered


def _memory_visible_tags(tags: list[str]) -> list[str]:
    return [tag for tag in tags if not str(tag).strip().lower().startswith(MEMORY_SCOPE_TAG_PREFIX)]


def _memory_entry_scope(entry: MemoryEntry) -> str:
    tagged = _memory_scope_from_tags(entry.tags)
    if tagged:
        return tagged
    return _infer_memory_scope(kind=str(entry.kind), source=str(entry.source))


def _memory_policy_scopes_for_query(query: str) -> list[str]:
    tokens = {token for token in re.findall(r"[a-z0-9_']+", str(query or "").lower()) if token}
    if not tokens:
        return sorted(MEMORY_SCOPES)
    for scope, hints in MEMORY_QUERY_SCOPE_HINTS.items():
        if tokens & hints:
            return sorted({scope, "preferences"})
    return sorted(MEMORY_SCOPES)


def _memory_requested_scopes(scopes_value: Any, *, query: str = "") -> list[str]:
    if isinstance(scopes_value, list):
        cleaned = []
        for item in scopes_value:
            scope = _normalize_memory_scope(item)
            if scope and scope not in cleaned:
                cleaned.append(scope)
        if cleaned:
            return cleaned
    fallback_single = _normalize_memory_scope(scopes_value)
    if fallback_single:
        return [fallback_single]
    return _memory_policy_scopes_for_query(query)


def _memory_confidence_score(entry: MemoryEntry, *, now_ts: float | None = None) -> float:
    now = time.time() if now_ts is None else float(now_ts)
    age_days = max(0.0, (now - float(entry.created_at)) / 86_400.0)
    recency = math.exp(-(age_days / 30.0))
    source_text = str(getattr(entry, "source", "")).strip().lower()
    if source_text.startswith("integration.") or source_text in {"user", "profile", "operator", "system"}:
        source_confidence = 0.9
    elif source_text:
        source_confidence = 0.7
    else:
        source_confidence = 0.5
    retrieval_score = float(getattr(entry, "score", 0.0) or 0.0)
    if not math.isfinite(retrieval_score) or retrieval_score <= 0.0:
        retrieval_score = float(getattr(entry, "importance", 0.5) or 0.5)
    sensitivity = _as_float(getattr(entry, "sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    confidence = (0.55 * retrieval_score) + (0.30 * recency) + (0.15 * source_confidence)
    confidence *= max(0.4, 1.0 - (0.35 * sensitivity))
    return _as_float(confidence, 0.0, minimum=0.0, maximum=1.0)


def _memory_confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _memory_source_trail(entry: MemoryEntry) -> str:
    source = str(getattr(entry, "source", "")).strip() or "unknown"
    created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(entry.created_at)))
    return f"id={entry.id};source={source};created_at={created}"


async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_add"):
        record_summary("memory_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_add", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    allow_pii = _as_bool(args.get("allow_pii"), default=False)
    if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
        _record_service_error("memory_add", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Potential PII detected in memory text. Use allow_pii=true only when intentional.",
                }
            ]
        }
    tags_raw = args.get("tags")
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    kind = str(args.get("kind", "note"))
    importance = _as_float(args.get("importance", 0.5), 0.5, minimum=0.0, maximum=1.0)
    sensitivity = _as_float(args.get("sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    source = str(args.get("source", "user"))
    requested_scope = args.get("scope")
    if requested_scope is not None and _normalize_memory_scope(requested_scope) is None:
        _record_service_error("memory_add", start_time, "invalid_data")
        scopes_text = ", ".join(sorted(MEMORY_SCOPES))
        return {"content": [{"type": "text", "text": f"scope must be one of: {scopes_text}."}]}
    scope = _memory_scope_for_add(kind=kind, source=source, tags=tags, requested_scope=requested_scope)
    tags = _memory_scope_tags(tags, scope)
    try:
        memory_id = _memory.add_memory(
            text,
            kind=kind,
            tags=tags,
            importance=importance,
            sensitivity=sensitivity,
            source=source,
        )
    except Exception as e:
        _record_service_error("memory_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory add failed: {e}"}]}
    record_summary("memory_add", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Memory stored (id={memory_id}, scope={scope})."}]}


async def memory_update(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_update"):
        record_summary("memory_update", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_update", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    memory_id = _as_exact_int(args.get("memory_id"))
    if memory_id is None or memory_id <= 0:
        _record_service_error("memory_update", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "memory_id must be a positive integer."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_update", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    allow_pii = _as_bool(args.get("allow_pii"), default=False)
    if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
        _record_service_error("memory_update", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Potential PII detected in memory text. Use allow_pii=true only when intentional.",
                }
            ]
        }
    try:
        updated = _memory.update_memory_text(memory_id, text)
    except Exception as e:
        _record_service_error("memory_update", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory update failed: {e}"}]}
    if not updated:
        _record_service_error("memory_update", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Memory not found."}]}
    record_summary("memory_update", "ok", start_time, effect=f"memory_id={memory_id}", risk="low")
    return {"content": [{"type": "text", "text": f"Memory updated (id={memory_id})."}]}


async def memory_forget(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_forget"):
        record_summary("memory_forget", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_forget", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    memory_id = _as_exact_int(args.get("memory_id"))
    if memory_id is None or memory_id <= 0:
        _record_service_error("memory_forget", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "memory_id must be a positive integer."}]}
    try:
        deleted = _memory.delete_memory(memory_id)
    except Exception as e:
        _record_service_error("memory_forget", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory forget failed: {e}"}]}
    if not deleted:
        _record_service_error("memory_forget", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Memory not found."}]}
    record_summary("memory_forget", "ok", start_time, effect=f"memory_id={memory_id}", risk="low")
    return {"content": [{"type": "text", "text": f"Memory forgotten (id={memory_id})."}]}


async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_search"):
        record_summary("memory_search", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_search", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    query = str(args.get("query", "")).strip()
    if not query:
        _record_service_error("memory_search", start_time, "missing_query")
        return {"content": [{"type": "text", "text": "Search query required."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    default_max_sensitivity = _as_float(
        getattr(_config, "memory_max_sensitivity", 0.4),
        0.4,
        minimum=0.0,
        maximum=1.0,
    )
    default_hybrid_weight = _as_float(
        getattr(_config, "memory_hybrid_weight", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    default_decay_enabled = _as_bool(getattr(_config, "memory_decay_enabled", False), default=False)
    default_decay_half_life_days = _as_float(
        getattr(_config, "memory_decay_half_life_days", 30.0),
        30.0,
        minimum=0.1,
    )
    default_mmr_enabled = _as_bool(getattr(_config, "memory_mmr_enabled", False), default=False)
    default_mmr_lambda = _as_float(
        getattr(_config, "memory_mmr_lambda", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    include_sensitive = _as_bool(args.get("include_sensitive"), default=False)
    max_sensitivity = None if include_sensitive else _as_float(
        args.get("max_sensitivity", default_max_sensitivity),
        default_max_sensitivity,
        minimum=0.0,
        maximum=1.0,
    )
    source_list = _as_str_list(args.get("sources"))
    scoped_policy = _memory_requested_scopes(args.get("scopes"), query=query)
    try:
        results = _memory.search_v2(
            query,
            limit=limit,
            max_sensitivity=max_sensitivity,
            hybrid_weight=_as_float(
                args.get("hybrid_weight", default_hybrid_weight),
                default_hybrid_weight,
                minimum=0.0,
                maximum=1.0,
            ),
            decay_enabled=_as_bool(args.get("decay_enabled"), default=default_decay_enabled),
            decay_half_life_days=_as_float(
                args.get("decay_half_life_days", default_decay_half_life_days),
                default_decay_half_life_days,
                minimum=0.1,
            ),
            mmr_enabled=_as_bool(args.get("mmr_enabled"), default=default_mmr_enabled),
            mmr_lambda=_as_float(
                args.get("mmr_lambda", default_mmr_lambda),
                default_mmr_lambda,
                minimum=0.0,
                maximum=1.0,
            ),
            sources=source_list,
        )
    except Exception as e:
        _record_service_error("memory_search", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory search failed: {e}"}]}
    scoped_results = []
    for entry in results:
        if _memory_entry_scope(entry) in scoped_policy:
            scoped_results.append(entry)
        if len(scoped_results) >= limit:
            break
    results = scoped_results
    if not results:
        record_summary("memory_search", "empty", start_time)
        return {"content": [{"type": "text", "text": f"No relevant memories found in scopes={','.join(scoped_policy)}."}]}
    lines = [f"Retrieval policy scopes={','.join(scoped_policy)}"]
    now_ts = time.time()
    for entry in results:
        visible_tags = _memory_visible_tags(entry.tags)
        tags = f" tags={','.join(visible_tags)}" if visible_tags else ""
        snippet = entry.text[:200]
        confidence_score = _memory_confidence_score(entry, now_ts=now_ts)
        confidence_label = _memory_confidence_label(confidence_score)
        source = str(entry.source).strip() or "unknown"
        scope = _memory_entry_scope(entry)
        trail = _memory_source_trail(entry)
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} score={entry.score:.2f} trail={trail} {snippet}{tags}"
        )
    record_summary("memory_search", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_status(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_status"):
        record_summary("memory_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_status", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    try:
        if _as_bool(args.get("warm"), default=False):
            _memory.warm()
        if _as_bool(args.get("sync"), default=False):
            _memory.sync()
        if _as_bool(args.get("optimize"), default=False):
            _memory.optimize()
        if _as_bool(args.get("vacuum"), default=False):
            _memory.vacuum()
        status = _memory.memory_status()
        if isinstance(status, dict):
            status["confidence_model"] = {
                "version": "v1",
                "inputs": ["retrieval_score", "recency", "source", "sensitivity"],
            }
            status["scope_policy"] = {
                "supported_scopes": sorted(MEMORY_SCOPES),
                "tag_prefix": MEMORY_SCOPE_TAG_PREFIX,
                "query_hints": {scope: sorted(hints) for scope, hints in MEMORY_QUERY_SCOPE_HINTS.items()},
                "default_scope": "preferences",
            }
    except Exception as e:
        _record_service_error("memory_status", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory status failed: {e}"}]}
    record_summary("memory_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status)}]}


async def memory_recent(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_recent"):
        record_summary("memory_recent", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_recent", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    kind = args.get("kind")
    source_list = _as_str_list(args.get("sources"))
    scoped_policy = _memory_requested_scopes(args.get("scopes"), query=str(args.get("query", "")))
    try:
        results = _memory.recent(limit=limit, kind=str(kind) if kind else None, sources=source_list)
    except Exception as e:
        _record_service_error("memory_recent", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory recent failed: {e}"}]}
    scoped_results = []
    for entry in results:
        if _memory_entry_scope(entry) in scoped_policy:
            scoped_results.append(entry)
        if len(scoped_results) >= limit:
            break
    results = scoped_results
    if not results:
        record_summary("memory_recent", "empty", start_time)
        return {"content": [{"type": "text", "text": f"No recent memories found in scopes={','.join(scoped_policy)}."}]}
    lines = [f"Retrieval policy scopes={','.join(scoped_policy)}"]
    now_ts = time.time()
    for entry in results:
        visible_tags = _memory_visible_tags(entry.tags)
        tags = f" tags={','.join(visible_tags)}" if visible_tags else ""
        snippet = entry.text[:200]
        confidence_score = _memory_confidence_score(entry, now_ts=now_ts)
        confidence_label = _memory_confidence_label(confidence_score)
        source = str(entry.source).strip() or "unknown"
        scope = _memory_entry_scope(entry)
        trail = _memory_source_trail(entry)
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} trail={trail} {snippet}{tags}"
        )
    record_summary("memory_recent", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_summary_add(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_add"):
        record_summary("memory_summary_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    topic = str(args.get("topic", "")).strip()
    summary = str(args.get("summary", "")).strip()
    if not topic or not summary:
        _record_service_error("memory_summary_add", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Summary topic and text required."}]}
    try:
        _memory.upsert_summary(topic, summary)
    except Exception as e:
        _record_service_error("memory_summary_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary add failed: {e}"}]}
    record_summary("memory_summary_add", "ok", start_time)
    return {"content": [{"type": "text", "text": "Summary stored."}]}


async def memory_summary_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_list"):
        record_summary("memory_summary_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    try:
        results = _memory.list_summaries(limit=limit)
    except Exception as e:
        _record_service_error("memory_summary_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary list failed: {e}"}]}
    if not results:
        record_summary("memory_summary_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No summaries found."}]}
    lines = [f"{summary.topic}: {summary.summary}" for summary in results]
    record_summary("memory_summary_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def task_plan_create(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_create"):
        record_summary("task_plan_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_create", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    title = str(args.get("title", "")).strip()
    steps = args.get("steps")
    if not title or not isinstance(steps, list) or not steps:
        _record_service_error("task_plan_create", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan title and steps required."}]}
    try:
        plan_id = _memory.add_task_plan(title, [str(step) for step in steps])
    except ValueError:
        _record_service_error("task_plan_create", start_time, "invalid_steps")
        return {"content": [{"type": "text", "text": "Plan requires at least one non-empty step."}]}
    except Exception as e:
        _record_service_error("task_plan_create", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan create failed: {e}"}]}
    record_summary("task_plan_create", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Plan created (id={plan_id})."}]}


async def task_plan_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_list"):
        record_summary("task_plan_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    open_only = _as_bool(args.get("open_only"), default=True)
    try:
        plans = _memory.list_task_plans(open_only=open_only)
    except Exception as e:
        _record_service_error("task_plan_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan list failed: {e}"}]}
    if not plans:
        record_summary("task_plan_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No task plans found."}]}
    blocks = []
    for plan in plans:
        header = f"Plan {plan.id}: {plan.title} ({plan.status})"
        steps = "\n".join([f"  {step.index + 1}. {step.text} [{step.status}]" for step in plan.steps])
        blocks.append(f"{header}\n{steps}")
    record_summary("task_plan_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}]}


async def task_plan_update(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_update"):
        record_summary("task_plan_update", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_update", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_exact_int(args.get("plan_id"))
    step_index = _as_exact_int(args.get("step_index"))
    status = str(args.get("status", "pending")).strip().lower()
    allowed_status = {"pending", "in_progress", "blocked", "done"}
    if plan_id is None or plan_id <= 0 or step_index is None or step_index < 0:
        _record_service_error("task_plan_update", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan id and step index required."}]}
    if status not in allowed_status:
        _record_service_error("task_plan_update", start_time, "invalid_status")
        return {"content": [{"type": "text", "text": "Status must be one of: pending, in_progress, blocked, done."}]}
    try:
        updated = _memory.update_task_step(plan_id, step_index, status)
    except Exception as e:
        _record_service_error("task_plan_update", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan update failed: {e}"}]}
    if not updated:
        record_summary("task_plan_update", "empty", start_time)
        return {"content": [{"type": "text", "text": "No task step updated."}]}
    record_summary("task_plan_update", "ok", start_time)
    return {"content": [{"type": "text", "text": "Plan updated."}]}


async def task_plan_summary(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_summary"):
        record_summary("task_plan_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_summary", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_exact_int(args.get("plan_id"))
    if plan_id is None or plan_id <= 0:
        _record_service_error("task_plan_summary", start_time, "missing_plan")
        return {"content": [{"type": "text", "text": "Plan id required."}]}
    try:
        progress = _memory.task_plan_progress(plan_id)
    except Exception as e:
        _record_service_error("task_plan_summary", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan summary failed: {e}"}]}
    if not progress:
        record_summary("task_plan_summary", "empty", start_time)
        return {"content": [{"type": "text", "text": "Plan not found."}]}
    done, total = progress
    text = f"Plan {plan_id}: {done}/{total} steps complete."
    record_summary("task_plan_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


async def task_plan_next(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_next"):
        record_summary("task_plan_next", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_next", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = args.get("plan_id")
    parsed_plan_id = _as_exact_int(plan_id) if plan_id is not None else None
    if plan_id is not None and (parsed_plan_id is None or parsed_plan_id <= 0):
        _record_service_error("task_plan_next", start_time, "invalid_plan")
        return {"content": [{"type": "text", "text": "Plan id must be a positive integer."}]}
    try:
        plan = _memory.next_task_step(parsed_plan_id) if parsed_plan_id else _memory.next_task_step()
    except Exception as e:
        _record_service_error("task_plan_next", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan next failed: {e}"}]}
    if not plan:
        record_summary("task_plan_next", "empty", start_time)
        return {"content": [{"type": "text", "text": "No pending steps found."}]}
    task_plan, step = plan
    text = f"Next step for plan {task_plan.id} ({task_plan.title}): {step.index + 1}. {step.text}"
    record_summary("task_plan_next", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


async def timer_create(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("timer_create"):
        record_summary("timer_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    duration = _duration_seconds(args.get("duration"))
    if duration is None:
        _record_service_error("timer_create", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Duration is required and must be a positive value like 90, 90s, 5m, or 1h 30m.",
                }
            ]
        }
    _prune_timers()
    if len(_timers) >= TIMER_MAX_ACTIVE:
        _record_service_error("timer_create", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Too many active timers ({TIMER_MAX_ACTIVE} max)."}]}
    label = str(args.get("label", "")).strip()
    now_wall = time.time()
    now_mono = time.monotonic()
    due_wall = now_wall + duration
    due_mono = now_mono + duration
    timer_id: int
    if _memory is not None:
        try:
            timer_id = _memory.add_timer(
                due_at=due_wall,
                duration_sec=duration,
                label=label,
                created_at=now_wall,
            )
        except Exception:
            _record_service_error("timer_create", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Timer create failed: persistent storage unavailable."}]}
    else:
        timer_id = _allocate_timer_id()
    _timers[timer_id] = {
        "id": timer_id,
        "label": label,
        "duration_sec": duration,
        "created_at": now_wall,
        "due_at": due_wall,
        "due_mono": due_mono,
    }
    record_summary("timer_create", "ok", start_time, effect=f"timer_id={timer_id}", risk="low")
    _audit(
        "timer_create",
        {
            "result": "ok",
            "timer_id": timer_id,
            "duration_sec": duration,
            "label": label,
        },
    )
    due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_wall))
    label_text = f" '{label}'" if label else ""
    return {
        "content": [
            {
                "type": "text",
                "text": f"Timer {timer_id}{label_text} set for {_format_duration(duration)} (due at {due_local}).",
            }
        ]
    }


async def timer_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("timer_list"):
        record_summary("timer_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    include_expired = _as_bool(args.get("include_expired"), default=False)
    if not include_expired:
        _prune_timers()
    now = time.monotonic()
    rows = sorted(_timers.values(), key=lambda item: float(item.get("due_mono", now)))
    if not rows:
        record_summary("timer_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No active timers."}]}
    lines: list[str] = []
    for payload in rows:
        timer_id = int(payload.get("id", 0))
        label = str(payload.get("label", "")).strip()
        due_mono = float(payload.get("due_mono", now))
        due_wall = float(payload.get("due_at", time.time()))
        remaining = due_mono - now
        if remaining <= 0.0:
            if not include_expired:
                continue
            status = f"expired { _format_duration(abs(remaining)) } ago"
        else:
            status = f"due in {_format_duration(remaining)}"
        due_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(due_wall))
        label_part = f" ({label})" if label else ""
        lines.append(f"- {timer_id}{label_part}: {status}; at {due_local}")
    if not lines:
        record_summary("timer_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No active timers."}]}
    record_summary("timer_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def timer_cancel(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("timer_cancel"):
        record_summary("timer_cancel", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    timer_id_raw = args.get("timer_id")
    label = str(args.get("label", "")).strip()
    parsed_timer_id = _as_exact_int(timer_id_raw) if timer_id_raw is not None else None
    if timer_id_raw is not None and (parsed_timer_id is None or parsed_timer_id <= 0):
        _record_service_error("timer_cancel", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "timer_id must be a positive integer."}]}
    if parsed_timer_id is None and not label:
        _record_service_error("timer_cancel", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Provide timer_id or label to cancel a timer."}]}
    _prune_timers()
    selected_id: int | None = None
    if parsed_timer_id is not None:
        if parsed_timer_id in _timers:
            selected_id = parsed_timer_id
    else:
        lowered = label.lower()
        for payload in sorted(_timers.values(), key=lambda item: float(item.get("due_mono", 0.0))):
            if str(payload.get("label", "")).strip().lower() == lowered:
                selected_id = int(payload.get("id", 0))
                break
    if selected_id is None:
        _record_service_error("timer_cancel", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Timer not found."}]}
    if _memory is not None:
        try:
            cancelled = _memory.cancel_timer(selected_id)
        except Exception:
            _record_service_error("timer_cancel", start_time, "storage_error")
            return {"content": [{"type": "text", "text": "Timer cancel failed: persistent storage unavailable."}]}
        if not cancelled:
            _record_service_error("timer_cancel", start_time, "not_found")
            return {"content": [{"type": "text", "text": "Timer not found."}]}
    removed = _timers.pop(selected_id, None)
    if removed is None:
        _record_service_error("timer_cancel", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Timer not found."}]}
    record_summary("timer_cancel", "ok", start_time, effect=f"timer_id={selected_id}", risk="low")
    _audit(
        "timer_cancel",
        {
            "result": "ok",
            "timer_id": selected_id,
            "label": str(removed.get("label", "")),
        },
    )
    return {"content": [{"type": "text", "text": f"Cancelled timer {selected_id}."}]}


async def tool_summary(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("tool_summary"):
        record_summary("tool_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
    except Exception as e:
        _record_service_error("tool_summary", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(summaries, default=str)}]}


async def tool_summary_text(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("tool_summary_text"):
        record_summary("tool_summary_text", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 6), 6, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
        text = _format_tool_summaries(summaries)
    except Exception as e:
        _record_service_error("tool_summary_text", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary_text", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


# ── Build MCP server ──────────────────────────────────────────

smart_home_tool = tool(
    "smart_home",
    "Control smart home devices via Home Assistant. "
    "For destructive actions (unlock doors, disable alarms, open covers), set dry_run=true first. "
    "Always explain what you're about to do before executing.",
    SERVICE_TOOL_SCHEMAS["smart_home"],
)(smart_home)


smart_home_state_tool = tool(
    "smart_home_state",
    "Get the current state of a Home Assistant entity.",
    SERVICE_TOOL_SCHEMAS["smart_home_state"],
)(smart_home_state)

home_assistant_capabilities_tool = tool(
    "home_assistant_capabilities",
    "Inspect a Home Assistant entity and list available domain services for safer planning.",
    SERVICE_TOOL_SCHEMAS["home_assistant_capabilities"],
)(home_assistant_capabilities)

home_assistant_conversation_tool = tool(
    "home_assistant_conversation",
    "Send a natural language command to Home Assistant's conversation API. Requires confirm=true.",
    SERVICE_TOOL_SCHEMAS["home_assistant_conversation"],
)(home_assistant_conversation)

home_assistant_todo_tool = tool(
    "home_assistant_todo",
    "Manage Home Assistant to-do entities (list/add/remove).",
    SERVICE_TOOL_SCHEMAS["home_assistant_todo"],
)(home_assistant_todo)

home_assistant_timer_tool = tool(
    "home_assistant_timer",
    "Control Home Assistant timer entities (state/start/pause/cancel/finish).",
    SERVICE_TOOL_SCHEMAS["home_assistant_timer"],
)(home_assistant_timer)

home_assistant_area_entities_tool = tool(
    "home_assistant_area_entities",
    "Resolve entities in a Home Assistant area, optionally including live state.",
    SERVICE_TOOL_SCHEMAS["home_assistant_area_entities"],
)(home_assistant_area_entities)

media_control_tool = tool(
    "media_control",
    "Control media_player entities with a simplified action interface.",
    SERVICE_TOOL_SCHEMAS["media_control"],
)(media_control)

weather_lookup_tool = tool(
    "weather_lookup",
    "Fetch current weather using the Open-Meteo provider.",
    SERVICE_TOOL_SCHEMAS["weather_lookup"],
)(weather_lookup)

webhook_trigger_tool = tool(
    "webhook_trigger",
    "Send an outbound webhook request to an allowlisted host.",
    SERVICE_TOOL_SCHEMAS["webhook_trigger"],
)(webhook_trigger)

webhook_inbound_list_tool = tool(
    "webhook_inbound_list",
    "List recently received inbound webhook callback events.",
    SERVICE_TOOL_SCHEMAS["webhook_inbound_list"],
)(webhook_inbound_list)

webhook_inbound_clear_tool = tool(
    "webhook_inbound_clear",
    "Clear stored inbound webhook callback events.",
    SERVICE_TOOL_SCHEMAS["webhook_inbound_clear"],
)(webhook_inbound_clear)

slack_notify_tool = tool(
    "slack_notify",
    "Send a Slack notification via incoming webhook.",
    SERVICE_TOOL_SCHEMAS["slack_notify"],
)(slack_notify)

discord_notify_tool = tool(
    "discord_notify",
    "Send a Discord notification via webhook.",
    SERVICE_TOOL_SCHEMAS["discord_notify"],
)(discord_notify)

email_send_tool = tool(
    "email_send",
    "Send an email through configured SMTP. Requires confirm=true.",
    SERVICE_TOOL_SCHEMAS["email_send"],
)(email_send)

email_summary_tool = tool(
    "email_summary",
    "Summarize recently sent emails recorded by Jarvis.",
    SERVICE_TOOL_SCHEMAS["email_summary"],
)(email_summary)

todoist_add_task_tool = tool(
    "todoist_add_task",
    "Create a task in Todoist (project configurable via env).",
    SERVICE_TOOL_SCHEMAS["todoist_add_task"],
)(todoist_add_task)

todoist_list_tasks_tool = tool(
    "todoist_list_tasks",
    "List active tasks from Todoist.",
    SERVICE_TOOL_SCHEMAS["todoist_list_tasks"],
)(todoist_list_tasks)

pushover_notify_tool = tool(
    "pushover_notify",
    "Send a push notification via Pushover.",
    SERVICE_TOOL_SCHEMAS["pushover_notify"],
)(pushover_notify)


get_time_tool = tool(
    "get_time",
    "Get the current local time (device clock).",
    SERVICE_TOOL_SCHEMAS["get_time"],
)(get_time)

system_status_tool = tool(
    "system_status",
    "Report current runtime capabilities and health snapshot.",
    SERVICE_TOOL_SCHEMAS["system_status"],
)(system_status)

system_status_contract_tool = tool(
    "system_status_contract",
    "Return the stable system_status schema contract for automation clients.",
    SERVICE_TOOL_SCHEMAS["system_status_contract"],
)(system_status_contract)

jarvis_scorecard_tool = tool(
    "jarvis_scorecard",
    "Return a unified scorecard across latency, reliability, initiative, and trust.",
    SERVICE_TOOL_SCHEMAS["jarvis_scorecard"],
)(jarvis_scorecard)

memory_add_tool = tool(
    "memory_add",
    "Store a long-term memory (facts, preferences, summaries).",
    SERVICE_TOOL_SCHEMAS["memory_add"],
)(memory_add)

memory_update_tool = tool(
    "memory_update",
    "Update existing memory text by id.",
    SERVICE_TOOL_SCHEMAS["memory_update"],
)(memory_update)

memory_forget_tool = tool(
    "memory_forget",
    "Forget (delete) a memory by id.",
    SERVICE_TOOL_SCHEMAS["memory_forget"],
)(memory_forget)

memory_search_tool = tool(
    "memory_search",
    "Search long-term memory for relevant entries.",
    SERVICE_TOOL_SCHEMAS["memory_search"],
)(memory_search)

memory_status_tool = tool(
    "memory_status",
    "Report memory index status and availability.",
    SERVICE_TOOL_SCHEMAS["memory_status"],
)(memory_status)

memory_recent_tool = tool(
    "memory_recent",
    "List recent memory entries.",
    SERVICE_TOOL_SCHEMAS["memory_recent"],
)(memory_recent)

memory_summary_add_tool = tool(
    "memory_summary_add",
    "Store or update a short memory summary for a topic.",
    SERVICE_TOOL_SCHEMAS["memory_summary_add"],
)(memory_summary_add)

memory_summary_list_tool = tool(
    "memory_summary_list",
    "List recent memory summaries.",
    SERVICE_TOOL_SCHEMAS["memory_summary_list"],
)(memory_summary_list)

task_plan_create_tool = tool(
    "task_plan_create",
    "Create a multi-step task plan and store it.",
    SERVICE_TOOL_SCHEMAS["task_plan_create"],
)(task_plan_create)

task_plan_list_tool = tool(
    "task_plan_list",
    "List stored task plans (optionally open only).",
    SERVICE_TOOL_SCHEMAS["task_plan_list"],
)(task_plan_list)

task_plan_update_tool = tool(
    "task_plan_update",
    "Update a task plan step status.",
    SERVICE_TOOL_SCHEMAS["task_plan_update"],
)(task_plan_update)

task_plan_summary_tool = tool(
    "task_plan_summary",
    "Summarize progress for a task plan.",
    SERVICE_TOOL_SCHEMAS["task_plan_summary"],
)(task_plan_summary)

task_plan_next_tool = tool(
    "task_plan_next",
    "Get the next pending step in a task plan.",
    SERVICE_TOOL_SCHEMAS["task_plan_next"],
)(task_plan_next)

timer_create_tool = tool(
    "timer_create",
    "Create a countdown timer.",
    SERVICE_TOOL_SCHEMAS["timer_create"],
)(timer_create)

timer_list_tool = tool(
    "timer_list",
    "List active timers and their remaining time.",
    SERVICE_TOOL_SCHEMAS["timer_list"],
)(timer_list)

timer_cancel_tool = tool(
    "timer_cancel",
    "Cancel an active timer by id or label.",
    SERVICE_TOOL_SCHEMAS["timer_cancel"],
)(timer_cancel)

reminder_create_tool = tool(
    "reminder_create",
    "Create a reminder with a due time.",
    SERVICE_TOOL_SCHEMAS["reminder_create"],
)(reminder_create)

reminder_list_tool = tool(
    "reminder_list",
    "List reminders and due status.",
    SERVICE_TOOL_SCHEMAS["reminder_list"],
)(reminder_list)

reminder_complete_tool = tool(
    "reminder_complete",
    "Mark a reminder as completed.",
    SERVICE_TOOL_SCHEMAS["reminder_complete"],
)(reminder_complete)

reminder_notify_due_tool = tool(
    "reminder_notify_due",
    "Send Pushover notifications for due reminders that have not been notified yet.",
    SERVICE_TOOL_SCHEMAS["reminder_notify_due"],
)(reminder_notify_due)

calendar_events_tool = tool(
    "calendar_events",
    "List calendar events from Home Assistant within a time window.",
    SERVICE_TOOL_SCHEMAS["calendar_events"],
)(calendar_events)

calendar_next_event_tool = tool(
    "calendar_next_event",
    "Fetch the next upcoming calendar event from Home Assistant.",
    SERVICE_TOOL_SCHEMAS["calendar_next_event"],
)(calendar_next_event)

tool_summary_tool = tool(
    "tool_summary",
    "Return recent tool execution summaries (latency/outcome).",
    SERVICE_TOOL_SCHEMAS["tool_summary"],
)(tool_summary)

tool_summary_text_tool = tool(
    "tool_summary_text",
    "Summarize recent tool executions for the user.",
    SERVICE_TOOL_SCHEMAS["tool_summary_text"],
)(tool_summary_text)

skills_list_tool = tool(
    "skills_list",
    "List discovered skills and their lifecycle status.",
    SERVICE_TOOL_SCHEMAS["skills_list"],
)(skills_list)

skills_enable_tool = tool(
    "skills_enable",
    "Enable a discovered skill by name.",
    SERVICE_TOOL_SCHEMAS["skills_enable"],
)(skills_enable)

skills_disable_tool = tool(
    "skills_disable",
    "Disable a discovered skill by name.",
    SERVICE_TOOL_SCHEMAS["skills_disable"],
)(skills_disable)

skills_version_tool = tool(
    "skills_version",
    "Return a skill version by name.",
    SERVICE_TOOL_SCHEMAS["skills_version"],
)(skills_version)

def create_services_server():
    return create_sdk_mcp_server(
        name="jarvis-services",
        version="0.1.0",
        tools=[
            smart_home_tool,
            smart_home_state_tool,
            home_assistant_capabilities_tool,
            home_assistant_conversation_tool,
            home_assistant_todo_tool,
            home_assistant_timer_tool,
            home_assistant_area_entities_tool,
            media_control_tool,
            weather_lookup_tool,
            webhook_trigger_tool,
            webhook_inbound_list_tool,
            webhook_inbound_clear_tool,
            slack_notify_tool,
            discord_notify_tool,
            email_send_tool,
            email_summary_tool,
            todoist_add_task_tool,
            todoist_list_tasks_tool,
            pushover_notify_tool,
            get_time_tool,
            system_status_tool,
            system_status_contract_tool,
            jarvis_scorecard_tool,
            tool_summary_tool,
            tool_summary_text_tool,
            skills_list_tool,
            skills_enable_tool,
            skills_disable_tool,
            skills_version_tool,
            memory_add_tool,
            memory_update_tool,
            memory_forget_tool,
            memory_search_tool,
            memory_recent_tool,
            memory_status_tool,
            memory_summary_add_tool,
            memory_summary_list_tool,
            task_plan_create_tool,
            task_plan_list_tool,
            task_plan_update_tool,
            task_plan_summary_tool,
            task_plan_next_tool,
            timer_create_tool,
            timer_list_tool,
            timer_cancel_tool,
            reminder_create_tool,
            reminder_list_tool,
            reminder_complete_tool,
            reminder_notify_due_tool,
            calendar_events_tool,
            calendar_next_event_tool,
        ],
    )
