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
from contextlib import suppress  # noqa: F401  # accessed by domain modules via services module alias
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
from jarvis.tool_summary import record_summary, list_summaries  # noqa: F401  # accessed via services module alias
from jarvis.memory import MemoryEntry, MemoryStore
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES, normalize_service_error_code
from jarvis.tools.service_schemas import (
    SERVICE_RUNTIME_REQUIRED_FIELDS,  # noqa: F401  # compatibility export for tests/importers
    SERVICE_TOOL_SCHEMAS,
)
from jarvis.tools.services_domains.home import (
    home_orchestrator,
    smart_home,
    smart_home_state,
    home_assistant_capabilities,
    home_assistant_conversation,
    home_assistant_todo,
    home_assistant_timer,
    home_assistant_area_entities,
    media_control,
)
from jarvis.tools.services_domains.planner import (
    planner_engine,
    task_plan_create,
    task_plan_list,
    task_plan_update,
    task_plan_summary,
    task_plan_next,
    timer_create,
    timer_list,
    timer_cancel,
    reminder_create,
    reminder_list,
    reminder_complete,
    reminder_notify_due,
)
from jarvis.tools.services_domains.integrations import (
    integration_hub,
    weather_lookup,
    webhook_trigger,
    webhook_inbound_list,
    webhook_inbound_clear,
    dead_letter_list,
    dead_letter_replay,
    calendar_events,
    calendar_next_event,
)
from jarvis.tools.services_domains.comms import (
    slack_notify,
    discord_notify,
    email_send,
    email_summary,
    todoist_add_task,
    todoist_list_tasks,
    pushover_notify,
)
from jarvis.tools.services_domains.governance import (
    tool_summary,
    tool_summary_text,
    skills_list,
    skills_enable,
    skills_disable,
    skills_version,
    system_status,
    system_status_contract,
    jarvis_scorecard,
    skills_governance,
    quality_evaluator,
    embodiment_presence,
)
from jarvis.tools.services_domains.trust import (
    proactive_assistant,
    memory_add,
    memory_update,
    memory_forget,
    memory_search,
    memory_status,
    memory_recent,
    memory_summary_add,
    memory_summary_list,
    memory_governance,
    identity_trust,
)

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency fallback
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Audit log in user's home dir for predictable location
AUDIT_LOG = Path.home() / ".jarvis" / "audit.jsonl"
DEFAULT_RECOVERY_JOURNAL = Path.home() / ".jarvis" / "recovery-journal.jsonl"
DEFAULT_DEAD_LETTER_QUEUE = Path.home() / ".jarvis" / "dead-letter-queue.jsonl"
DEFAULT_EXPANSION_STATE = Path.home() / ".jarvis" / "expansion-state.json"
DEFAULT_RELEASE_CHANNEL_CONFIG = Path("config/release-channels.json")

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
SYSTEM_STATUS_CONTRACT_VERSION = "2.0"
HA_CONVERSATION_MAX_TEXT_CHARS = 600
TIMER_MAX_SECONDS = 86_400.0
TIMER_MAX_ACTIVE = 200
REMINDER_MAX_ACTIVE = 500
CALENDAR_DEFAULT_WINDOW_HOURS = 24.0
CALENDAR_MAX_WINDOW_HOURS = 24.0 * 31.0
PLAN_PREVIEW_TTL_SEC = 300.0
PLAN_PREVIEW_MAX_PENDING = 1000
CACHED_QUALITY_REPORT_MAX = 32
GUEST_SESSION_DEFAULT_TTL_SEC = 3600.0
GUEST_SESSION_MAX_TTL_SEC = 24.0 * 3600.0
HOME_TASK_MAX_TRACKED = 400
PLANNER_TASK_GRAPH_MAX = 300
DEFERRED_ACTION_MAX = 500
HOME_AUTOMATION_MAX_TRACKED = 300
AUTONOMY_CYCLE_HISTORY_MAX = 200
QUALITY_REPORT_DIR_DEFAULT = Path.home() / ".jarvis" / "quality-reports"
NOTES_CAPTURE_DIR_DEFAULT = Path.home() / ".jarvis" / "notes"
RELEASE_CHANNELS = {"dev", "beta", "stable"}
NOTION_API_VERSION = "2022-06-28"
SKILL_SANDBOX_TEMPLATES: dict[str, dict[str, Any]] = {
    "read-only": {
        "filesystem": "read_only",
        "network": "allow",
        "writes": [],
        "description": "Read-only filesystem with normal outbound access.",
    },
    "network-limited": {
        "filesystem": "read_write",
        "network": "allowlist",
        "writes": ["workspace"],
        "description": "Write-capable workspace with explicit outbound allowlist.",
    },
    "local-only": {
        "filesystem": "read_write",
        "network": "deny",
        "writes": ["workspace"],
        "description": "No outbound networking; local operations only.",
    },
}
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
_notion_api_token: str = ""
_notion_database_id: str = ""
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
_dead_letter_queue_path: Path = DEFAULT_DEAD_LETTER_QUEUE
_expansion_state_path: Path = DEFAULT_EXPANSION_STATE
_release_channel_config_path: Path = DEFAULT_RELEASE_CHANNEL_CONFIG
_quality_report_dir: Path = QUALITY_REPORT_DIR_DEFAULT
_notes_capture_dir: Path = NOTES_CAPTURE_DIR_DEFAULT
_proactive_state: dict[str, Any] = {
    "pending_follow_through": [],
    "digest_snoozed_until": 0.0,
    "last_briefing_at": 0.0,
    "last_digest_at": 0.0,
}
_memory_partition_overlays: dict[str, dict[str, Any]] = {}
_memory_quality_last: dict[str, Any] = {}
_identity_trust_policies: dict[str, dict[str, Any]] = {}
_guest_sessions: dict[str, dict[str, Any]] = {}
_household_profiles: dict[str, dict[str, Any]] = {}
_home_area_policies: dict[str, dict[str, Any]] = {}
_home_task_runs: dict[str, dict[str, Any]] = {}
_home_task_seq: int = 1
_home_automation_drafts: dict[str, dict[str, Any]] = {}
_home_automation_applied: dict[str, dict[str, Any]] = {}
_home_automation_seq: int = 1
_skill_quotas: dict[str, dict[str, Any]] = {}
_planner_task_graphs: dict[str, dict[str, Any]] = {}
_planner_task_seq: int = 1
_deferred_actions: dict[str, dict[str, Any]] = {}
_deferred_action_seq: int = 1
_autonomy_checkpoints: dict[str, dict[str, Any]] = {}
_autonomy_cycle_history: list[dict[str, Any]] = []
_quality_reports: list[dict[str, Any]] = []
_micro_expression_library: dict[str, dict[str, Any]] = {}
_gaze_calibrations: dict[str, dict[str, Any]] = {}
_gesture_envelopes: dict[str, dict[str, Any]] = {}
_privacy_posture: dict[str, Any] = {
    "state": "normal",
    "reason": "startup",
    "updated_at": 0.0,
}
_motion_safety_envelope: dict[str, Any] = {
    "proximity_limit_cm": 35.0,
    "max_yaw_deg": 45.0,
    "max_pitch_deg": 20.0,
    "max_roll_deg": 15.0,
    "hardware_state": "normal",
    "updated_at": 0.0,
}
_release_channel_state: dict[str, Any] = {
    "active_channel": "dev",
    "last_check_at": 0.0,
    "last_check_channel": "",
    "last_check_passed": False,
    "migration_checks": [],
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
    global _notion_api_token, _notion_database_id
    global _weather_units, _weather_timeout_sec
    global _webhook_allowlist, _webhook_auth_token, _webhook_timeout_sec
    global _turn_timeout_listen_sec, _turn_timeout_think_sec, _turn_timeout_speak_sec, _turn_timeout_act_sec
    global _slack_webhook_url, _discord_webhook_url
    global _identity_enforcement_enabled, _identity_default_user, _identity_default_profile
    global _identity_user_profiles, _identity_trusted_users, _identity_require_approval, _identity_approval_code
    global _plan_preview_require_ack, _safe_mode_enabled
    global _memory_retention_days, _audit_retention_days
    global _memory_pii_guardrails_enabled, _audit_encryption_enabled, _data_encryption_key
    global _timer_id_seq, _reminder_id_seq, _integration_circuit_breakers, _recovery_journal_path, _dead_letter_queue_path
    global _expansion_state_path, _release_channel_config_path, _quality_report_dir, _notes_capture_dir
    global _home_task_seq, _home_automation_seq, _planner_task_seq, _deferred_action_seq
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
    _notion_api_token = str(getattr(config, "notion_api_token", "")).strip()
    _notion_database_id = str(getattr(config, "notion_database_id", "")).strip()
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
    _dead_letter_queue_path = Path(
        str(getattr(config, "dead_letter_queue_path", str(DEFAULT_DEAD_LETTER_QUEUE)))
    ).expanduser()
    _expansion_state_path = Path(
        str(getattr(config, "expansion_state_path", str(DEFAULT_EXPANSION_STATE)))
    ).expanduser()
    _release_channel_config_path = Path(
        str(getattr(config, "release_channel_config_path", str(DEFAULT_RELEASE_CHANNEL_CONFIG)))
    ).expanduser()
    _quality_report_dir = Path(
        str(getattr(config, "quality_report_dir", str(QUALITY_REPORT_DIR_DEFAULT)))
    ).expanduser()
    _notes_capture_dir = Path(
        str(getattr(config, "notes_capture_dir", str(NOTES_CAPTURE_DIR_DEFAULT)))
    ).expanduser()
    if not _release_channel_config_path.is_absolute():
        _release_channel_config_path = (Path.cwd() / _release_channel_config_path).resolve()
    if not _quality_report_dir.is_absolute():
        _quality_report_dir = (Path.cwd() / _quality_report_dir).resolve()
    if not _notes_capture_dir.is_absolute():
        _notes_capture_dir = (Path.cwd() / _notes_capture_dir).resolve()
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
    _proactive_state["pending_follow_through"] = []
    _proactive_state["digest_snoozed_until"] = 0.0
    _proactive_state["last_briefing_at"] = 0.0
    _proactive_state["last_digest_at"] = 0.0
    _memory_partition_overlays.clear()
    _memory_quality_last.clear()
    _identity_trust_policies.clear()
    _guest_sessions.clear()
    _household_profiles.clear()
    _home_area_policies.clear()
    _home_task_runs.clear()
    _home_automation_drafts.clear()
    _home_automation_applied.clear()
    _skill_quotas.clear()
    _planner_task_graphs.clear()
    _deferred_actions.clear()
    _autonomy_checkpoints.clear()
    _autonomy_cycle_history.clear()
    _quality_reports.clear()
    _micro_expression_library.clear()
    _gaze_calibrations.clear()
    _gesture_envelopes.clear()
    _privacy_posture["state"] = "normal"
    _privacy_posture["reason"] = "startup"
    _privacy_posture["updated_at"] = 0.0
    _motion_safety_envelope["updated_at"] = 0.0
    _release_channel_state["active_channel"] = "dev"
    _release_channel_state["last_check_at"] = 0.0
    _release_channel_state["last_check_channel"] = ""
    _release_channel_state["last_check_passed"] = False
    _release_channel_state["migration_checks"] = []
    _home_task_seq = 1
    _home_automation_seq = 1
    _planner_task_seq = 1
    _deferred_action_seq = 1
    for integration in sorted(set(INTEGRATION_TOOL_MAP.values())):
        _ensure_circuit_breaker_state(integration)
    _load_expansion_state()
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
    guest_token = str(
        payload.get("guest_session_token")
        or context_payload.get("guest_session_token")
        or ""
    ).strip()
    guest_session = _resolve_guest_session(guest_token) if guest_token else None

    if guest_session is not None:
        speaker_verified = _as_bool(
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
            "guest_capabilities": _as_str_list(guest_session.get("capabilities"), lower=True),
            "guest_expires_at": float(guest_session.get("expires_at", 0.0) or 0.0),
        }

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
        "profile": _identity_profile_level(profile),
        "trusted": trusted,
        "speaker_verified": speaker_verified,
        "source": source,
        "guest_session_token": "",
        "guest_capabilities": [],
        "guest_expires_at": 0.0,
    }


def _identity_audit_fields(context: dict[str, Any], decision_chain: list[str] | None = None) -> dict[str, Any]:
    chain = [str(item) for item in (decision_chain or []) if str(item).strip()]
    if not chain:
        chain = ["identity_context_applied"]
    return {
        "requester_id": str(context.get("requester_id", "")),
        "requester_profile": _identity_profile_level(str(context.get("profile", "control"))),
        "requester_trusted": bool(context.get("trusted", False)),
        "speaker_verified": bool(context.get("speaker_verified", False)),
        "identity_source": str(context.get("source", "default")),
        "guest_session_token": str(context.get("guest_session_token", "")),
        "guest_expires_at": float(context.get("guest_expires_at", 0.0) or 0.0),
        "decision_chain": chain,
    }


def _identity_trust_domain(tool_name: str, args: dict[str, Any] | None) -> str:
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


def _identity_authorize(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    mutating: bool,
    high_risk: bool,
) -> tuple[bool, str | None, dict[str, Any], list[str]]:
    context = _identity_context(args)
    payload = args if isinstance(args, dict) else {}
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
    if _identity_profile_level(str(context.get("profile", "control"))) == "guest":
        guest_caps = {
            item
            for item in _as_str_list(context.get("guest_capabilities"), lower=True)
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

    if not _identity_enforcement_enabled:
        chain.append("identity_enforcement_disabled")
        return True, None, context, chain

    profile = _identity_profile_level(str(context.get("profile", "control")))
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
    domain = _identity_trust_domain(tool_name, payload)
    policy = _identity_trust_policies.get(domain, {})
    required_profile = _identity_profile_level(str(policy.get("required_profile", "control")))
    if _profile_rank(profile) < _profile_rank(required_profile):
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
    if _as_bool(policy.get("requires_step_up"), default=False):
        if not (_as_bool(payload.get("approved"), default=False) or bool(payload.get("approval_code"))):
            chain.append("deny:step_up_required")
            return (
                False,
                f"Trust policy for domain '{domain}' requires step-up approval.",
                context,
                chain,
            )
        chain.append("trust_policy_step_up")
    if high_risk and _identity_require_approval:
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


def _identity_profile_level(profile: str) -> str:
    normalized = str(profile or "control").strip().lower()
    if normalized in {"deny", "guest", "readonly", "control", "trusted"}:
        return normalized
    return "control"


def _profile_rank(profile: str) -> int:
    order = {
        "deny": 0,
        "guest": 1,
        "readonly": 2,
        "control": 3,
        "trusted": 4,
    }
    return order.get(_identity_profile_level(profile), 3)


def _prune_guest_sessions(*, now_ts: float | None = None) -> None:
    if not _guest_sessions:
        return
    now = time.time() if now_ts is None else float(now_ts)
    expired = [
        token
        for token, row in _guest_sessions.items()
        if float(row.get("expires_at", 0.0) or 0.0) <= now
    ]
    for token in expired:
        _guest_sessions.pop(token, None)
    if expired:
        _persist_expansion_state()


def _resolve_guest_session(token: str, *, now_ts: float | None = None) -> dict[str, Any] | None:
    text = str(token or "").strip()
    if not text:
        return None
    _prune_guest_sessions(now_ts=now_ts)
    row = _guest_sessions.get(text)
    if not isinstance(row, dict):
        return None
    expires_at = float(row.get("expires_at", 0.0) or 0.0)
    now = time.time() if now_ts is None else float(now_ts)
    if expires_at <= now:
        _guest_sessions.pop(text, None)
        return None
    return row


def _register_guest_session(
    *,
    guest_id: str,
    capabilities: list[str],
    ttl_sec: float,
    now_ts: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now_ts is None else float(now_ts)
    ttl = _as_float(ttl_sec, GUEST_SESSION_DEFAULT_TTL_SEC, minimum=60.0, maximum=GUEST_SESSION_MAX_TTL_SEC)
    token = secrets.token_urlsafe(12)
    row = {
        "token": token,
        "guest_id": str(guest_id or "guest").strip().lower() or "guest",
        "capabilities": sorted(set(_as_str_list(capabilities, lower=True))),
        "issued_at": now,
        "expires_at": now + ttl,
    }
    _guest_sessions[token] = row
    _prune_guest_sessions(now_ts=now)
    return row


def _extract_area_from_entity(entity_id: str) -> str:
    text = str(entity_id or "").strip().lower()
    if "." not in text:
        return ""
    _, name = text.split(".", 1)
    cleaned = re.sub(r"[^a-z0-9_]", "_", name)
    parts = [part for part in cleaned.split("_") if part]
    if not parts:
        return ""
    if parts[0] in {"light", "switch", "media", "player", "climate", "lock", "cover"} and len(parts) > 1:
        return parts[1]
    return parts[0]


def _home_action_is_loud(*, domain: str, action: str, data: dict[str, Any] | None = None) -> bool:
    domain_text = str(domain or "").strip().lower()
    action_text = str(action or "").strip().lower()
    payload = data if isinstance(data, dict) else {}
    if domain_text == "media_player" and action_text in {"media_play", "play_media", "turn_on", "volume_set"}:
        return True
    if domain_text in {"light", "switch"} and action_text in {"turn_on", "toggle"}:
        brightness = payload.get("brightness")
        if brightness is None:
            return True
        try:
            level = float(brightness)
        except (TypeError, ValueError):
            return True
        return level >= 120.0
    return False


def _home_area_policy_violation(
    *,
    domain: str,
    action: str,
    entity_id: str,
    data: dict[str, Any] | None = None,
    now_ts: float | None = None,
) -> tuple[bool, str]:
    area = _extract_area_from_entity(entity_id)
    if not area:
        return False, ""
    policy = _home_area_policies.get(area)
    if not isinstance(policy, dict):
        return False, ""
    blocked_pairs = {
        item
        for item in _as_str_list(policy.get("blocked_actions"), lower=True)
        if ":" in item
    }
    pair = f"{str(domain).strip().lower()}:{str(action).strip().lower()}"
    if pair in blocked_pairs:
        return True, f"Area policy for '{area}' blocks action {pair}."
    quiet_start = str(policy.get("quiet_hours_start", "")).strip()
    quiet_end = str(policy.get("quiet_hours_end", "")).strip()
    if quiet_start and quiet_end:
        start = _hhmm_to_minutes(quiet_start)
        end = _hhmm_to_minutes(quiet_end)
        if start is not None and end is not None and start != end:
            local = time.localtime(time.time() if now_ts is None else float(now_ts))
            minute = (local.tm_hour * 60) + local.tm_min
            in_quiet = (start <= minute < end) if start < end else (minute >= start or minute < end)
            if in_quiet and _home_action_is_loud(domain=domain, action=action, data=data):
                return True, f"Area policy quiet hours are active for '{area}' and loud actions are blocked."
    return False, ""


def _quality_reports_snapshot(*, limit: int = 10) -> list[dict[str, Any]]:
    if not _quality_reports:
        return []
    capped = _as_int(limit, 10, minimum=1, maximum=50)
    return [dict(item) for item in _quality_reports[-capped:]][::-1]


def _append_quality_report(report: dict[str, Any]) -> None:
    _quality_reports.append({str(key): value for key, value in report.items()})
    if len(_quality_reports) > CACHED_QUALITY_REPORT_MAX:
        del _quality_reports[: len(_quality_reports) - CACHED_QUALITY_REPORT_MAX]
    _persist_expansion_state()


def _json_safe_clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_clone(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_clone(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _replace_state_dict(target: dict[str, Any], source: Any) -> None:
    target.clear()
    if not isinstance(source, dict):
        return
    target.update({str(key): _json_safe_clone(value) for key, value in source.items()})


def _expansion_state_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "saved_at": time.time(),
        "proactive_state": _json_safe_clone(_proactive_state),
        "memory_partition_overlays": _json_safe_clone(_memory_partition_overlays),
        "memory_quality_last": _json_safe_clone(_memory_quality_last),
        "identity_trust_policies": _json_safe_clone(_identity_trust_policies),
        "guest_sessions": _json_safe_clone(_guest_sessions),
        "household_profiles": _json_safe_clone(_household_profiles),
        "home_area_policies": _json_safe_clone(_home_area_policies),
        "home_task_runs": _json_safe_clone(_home_task_runs),
        "home_task_seq": int(_home_task_seq),
        "home_automation_drafts": _json_safe_clone(_home_automation_drafts),
        "home_automation_applied": _json_safe_clone(_home_automation_applied),
        "home_automation_seq": int(_home_automation_seq),
        "skill_quotas": _json_safe_clone(_skill_quotas),
        "planner_task_graphs": _json_safe_clone(_planner_task_graphs),
        "planner_task_seq": int(_planner_task_seq),
        "deferred_actions": _json_safe_clone(_deferred_actions),
        "deferred_action_seq": int(_deferred_action_seq),
        "autonomy_checkpoints": _json_safe_clone(_autonomy_checkpoints),
        "autonomy_cycle_history": _json_safe_clone(_autonomy_cycle_history[-AUTONOMY_CYCLE_HISTORY_MAX:]),
        "quality_reports": _json_safe_clone(_quality_reports[-CACHED_QUALITY_REPORT_MAX:]),
        "micro_expression_library": _json_safe_clone(_micro_expression_library),
        "gaze_calibrations": _json_safe_clone(_gaze_calibrations),
        "gesture_envelopes": _json_safe_clone(_gesture_envelopes),
        "privacy_posture": _json_safe_clone(_privacy_posture),
        "motion_safety_envelope": _json_safe_clone(_motion_safety_envelope),
        "release_channel_state": _json_safe_clone(_release_channel_state),
    }


def _persist_expansion_state() -> None:
    path = _expansion_state_path
    payload = _expansion_state_payload()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError:
        log.warning("Failed to persist expansion state", exc_info=True)


def _load_expansion_state() -> None:
    path = _expansion_state_path
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("Failed to load expansion state", exc_info=True)
        return
    if not isinstance(payload, dict):
        return

    proactive = payload.get("proactive_state")
    if isinstance(proactive, dict):
        pending = proactive.get("pending_follow_through")
        _proactive_state["pending_follow_through"] = (
            [_json_safe_clone(row) for row in pending if isinstance(row, dict)]
            if isinstance(pending, list)
            else []
        )
        _proactive_state["digest_snoozed_until"] = _as_float(
            proactive.get("digest_snoozed_until", 0.0),
            0.0,
            minimum=0.0,
        )
        _proactive_state["last_briefing_at"] = _as_float(
            proactive.get("last_briefing_at", 0.0),
            0.0,
            minimum=0.0,
        )
        _proactive_state["last_digest_at"] = _as_float(
            proactive.get("last_digest_at", 0.0),
            0.0,
            minimum=0.0,
        )

    _replace_state_dict(_memory_partition_overlays, payload.get("memory_partition_overlays"))
    _replace_state_dict(_memory_quality_last, payload.get("memory_quality_last"))
    _replace_state_dict(_identity_trust_policies, payload.get("identity_trust_policies"))
    _replace_state_dict(_household_profiles, payload.get("household_profiles"))
    _replace_state_dict(_home_area_policies, payload.get("home_area_policies"))
    _replace_state_dict(_home_task_runs, payload.get("home_task_runs"))
    _replace_state_dict(_home_automation_drafts, payload.get("home_automation_drafts"))
    _replace_state_dict(_home_automation_applied, payload.get("home_automation_applied"))
    _replace_state_dict(_skill_quotas, payload.get("skill_quotas"))
    _replace_state_dict(_planner_task_graphs, payload.get("planner_task_graphs"))
    _replace_state_dict(_deferred_actions, payload.get("deferred_actions"))
    _replace_state_dict(_autonomy_checkpoints, payload.get("autonomy_checkpoints"))
    _replace_state_dict(_micro_expression_library, payload.get("micro_expression_library"))
    _replace_state_dict(_gaze_calibrations, payload.get("gaze_calibrations"))
    _replace_state_dict(_gesture_envelopes, payload.get("gesture_envelopes"))

    autonomy_history = payload.get("autonomy_cycle_history")
    _autonomy_cycle_history.clear()
    if isinstance(autonomy_history, list):
        for row in autonomy_history[-AUTONOMY_CYCLE_HISTORY_MAX:]:
            if isinstance(row, dict):
                _autonomy_cycle_history.append({str(key): _json_safe_clone(value) for key, value in row.items()})

    _guest_sessions.clear()
    guest_sessions = payload.get("guest_sessions")
    if isinstance(guest_sessions, dict):
        now = time.time()
        for raw_token, raw_row in guest_sessions.items():
            token = str(raw_token).strip()
            if not token or not isinstance(raw_row, dict):
                continue
            expires_at = _as_float(raw_row.get("expires_at", 0.0), 0.0, minimum=0.0)
            if expires_at <= now:
                continue
            issued_at = _as_float(raw_row.get("issued_at", 0.0), 0.0, minimum=0.0)
            guest_id = str(raw_row.get("guest_id", "guest")).strip().lower() or "guest"
            capabilities = sorted(set(_as_str_list(raw_row.get("capabilities"), lower=True)))
            _guest_sessions[token] = {
                "token": token,
                "guest_id": guest_id,
                "capabilities": capabilities,
                "issued_at": issued_at,
                "expires_at": expires_at,
            }

    quality_rows = payload.get("quality_reports")
    _quality_reports.clear()
    if isinstance(quality_rows, list):
        for row in quality_rows[-CACHED_QUALITY_REPORT_MAX:]:
            if isinstance(row, dict):
                _quality_reports.append({str(key): _json_safe_clone(value) for key, value in row.items()})

    privacy_posture = payload.get("privacy_posture")
    if isinstance(privacy_posture, dict):
        _privacy_posture["state"] = str(privacy_posture.get("state", "normal")).strip().lower() or "normal"
        _privacy_posture["reason"] = str(privacy_posture.get("reason", "startup")).strip() or "startup"
        _privacy_posture["updated_at"] = _as_float(privacy_posture.get("updated_at", 0.0), 0.0, minimum=0.0)

    motion_envelope = payload.get("motion_safety_envelope")
    if isinstance(motion_envelope, dict):
        _motion_safety_envelope["proximity_limit_cm"] = _as_float(
            motion_envelope.get("proximity_limit_cm", _motion_safety_envelope.get("proximity_limit_cm", 35.0)),
            _as_float(_motion_safety_envelope.get("proximity_limit_cm", 35.0), 35.0),
            minimum=5.0,
            maximum=300.0,
        )
        _motion_safety_envelope["max_yaw_deg"] = _as_float(
            motion_envelope.get("max_yaw_deg", _motion_safety_envelope.get("max_yaw_deg", 45.0)),
            _as_float(_motion_safety_envelope.get("max_yaw_deg", 45.0), 45.0),
            minimum=0.0,
            maximum=180.0,
        )
        _motion_safety_envelope["max_pitch_deg"] = _as_float(
            motion_envelope.get("max_pitch_deg", _motion_safety_envelope.get("max_pitch_deg", 20.0)),
            _as_float(_motion_safety_envelope.get("max_pitch_deg", 20.0), 20.0),
            minimum=0.0,
            maximum=90.0,
        )
        _motion_safety_envelope["max_roll_deg"] = _as_float(
            motion_envelope.get("max_roll_deg", _motion_safety_envelope.get("max_roll_deg", 15.0)),
            _as_float(_motion_safety_envelope.get("max_roll_deg", 15.0), 15.0),
            minimum=0.0,
            maximum=90.0,
        )
        _motion_safety_envelope["hardware_state"] = (
            str(motion_envelope.get("hardware_state", "normal")).strip().lower() or "normal"
        )
        _motion_safety_envelope["updated_at"] = _as_float(
            motion_envelope.get("updated_at", 0.0),
            0.0,
            minimum=0.0,
        )

    release_state = payload.get("release_channel_state")
    if isinstance(release_state, dict):
        channel = str(release_state.get("active_channel", "dev")).strip().lower()
        if channel not in RELEASE_CHANNELS:
            channel = "dev"
        _release_channel_state["active_channel"] = channel
        _release_channel_state["last_check_at"] = _as_float(
            release_state.get("last_check_at", 0.0),
            0.0,
            minimum=0.0,
        )
        _release_channel_state["last_check_channel"] = (
            str(release_state.get("last_check_channel", channel)).strip().lower() or channel
        )
        _release_channel_state["last_check_passed"] = bool(release_state.get("last_check_passed", False))
        migration_checks = release_state.get("migration_checks")
        _release_channel_state["migration_checks"] = (
            [_json_safe_clone(row) for row in migration_checks if isinstance(row, dict)]
            if isinstance(migration_checks, list)
            else []
        )

    global _home_task_seq, _home_automation_seq, _planner_task_seq, _deferred_action_seq
    _home_task_seq = _as_int(payload.get("home_task_seq", 1), 1, minimum=1)
    _home_automation_seq = _as_int(payload.get("home_automation_seq", 1), 1, minimum=1)
    _planner_task_seq = _as_int(payload.get("planner_task_seq", 1), 1, minimum=1)
    _deferred_action_seq = _as_int(payload.get("deferred_action_seq", 1), 1, minimum=1)
    _prune_guest_sessions()


def _run_release_channel_check(base: Path, check: dict[str, Any]) -> dict[str, Any]:
    kind = str(check.get("type", "")).strip().lower()
    path = str(check.get("path", "")).strip()
    target = (base / path).resolve() if path else base

    if kind == "file_exists":
        ok = target.exists()
        return {"type": kind, "path": path, "ok": ok, "detail": "exists" if ok else "missing"}

    if kind == "text_contains":
        needle = str(check.get("needle", "")).strip()
        if not target.exists() or not target.is_file():
            return {"type": kind, "path": path, "needle": needle, "ok": False, "detail": "missing_file"}
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"type": kind, "path": path, "needle": needle, "ok": False, "detail": "read_failed"}
        ok = needle in text
        return {
            "type": kind,
            "path": path,
            "needle": needle,
            "ok": ok,
            "detail": "found" if ok else "missing_needle",
        }

    return {"type": kind or "unknown", "path": path, "ok": False, "detail": "unsupported_check_type"}


def _load_release_channel_config() -> tuple[dict[str, Any] | None, str]:
    path = _release_channel_config_path
    if not path.exists():
        return None, f"release channel config missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, f"release channel config unreadable: {path}"
    if not isinstance(payload, dict):
        return None, f"release channel config invalid format: {path}"
    return payload, ""


def _evaluate_release_channel(*, channel: str, workspace: Path | None = None) -> dict[str, Any]:
    normalized_channel = str(channel or "").strip().lower()
    if normalized_channel not in RELEASE_CHANNELS:
        return {
            "channel": normalized_channel,
            "passed": False,
            "check_count": 0,
            "failed_count": 1,
            "results": [],
            "migration_checks": [],
            "error": f"Unsupported release channel: {normalized_channel or '<empty>'}.",
        }

    config_payload, error = _load_release_channel_config()
    if config_payload is None:
        return {
            "channel": normalized_channel,
            "passed": False,
            "check_count": 0,
            "failed_count": 1,
            "results": [],
            "migration_checks": [],
            "error": error,
        }

    channels = config_payload.get("channels", {}) if isinstance(config_payload, dict) else {}
    channel_cfg = channels.get(normalized_channel, {}) if isinstance(channels, dict) else {}
    checks = channel_cfg.get("required_checks", []) if isinstance(channel_cfg, dict) else []
    root = (workspace or Path.cwd()).resolve()
    results = [_run_release_channel_check(root, row) for row in checks if isinstance(row, dict)]
    failed = [row for row in results if not bool(row.get("ok"))]
    migration_checks = [
        {
            "id": f"{normalized_channel}-{idx + 1}",
            "type": str(row.get("type", "unknown")),
            "path": str(row.get("path", "")),
            "status": "passed" if bool(row.get("ok")) else "failed",
            "detail": str(row.get("detail", "")),
        }
        for idx, row in enumerate(results)
    ]
    return {
        "channel": normalized_channel,
        "passed": len(failed) == 0,
        "check_count": len(results),
        "failed_count": len(failed),
        "results": results,
        "migration_checks": migration_checks,
        "config_path": str(_release_channel_config_path),
        "workspace": str(root),
    }


def _write_quality_report_artifact(payload: dict[str, Any], *, report_path: str | None = None) -> str:
    if report_path:
        path = Path(report_path).expanduser()
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = _quality_report_dir / f"quality-report-{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)


def _capture_note(*, backend: str, title: str, content: str, path_hint: str = "") -> dict[str, Any]:
    normalized_backend = str(backend or "local_markdown").strip().lower()
    clean_title = str(title or "jarvis-note").strip() or "jarvis-note"
    clean_content = str(content or "").strip()
    slug = re.sub(r"[^a-z0-9_-]+", "-", clean_title.lower()).strip("-") or "jarvis-note"
    if normalized_backend in {"obsidian", "local_markdown"}:
        base = Path(path_hint).expanduser() if path_hint else _notes_capture_dir
        base.mkdir(parents=True, exist_ok=True)
        file_path = base / f"{slug}.md"
        body = f"# {clean_title}\n\n{clean_content}\n"
        file_path.write_text(body)
        return {
            "backend": normalized_backend,
            "stored": True,
            "path": str(file_path),
        }
    if normalized_backend == "notion":
        return {
            "backend": normalized_backend,
            "stored": False,
            "status": "draft_only",
            "detail": "Notion API bridge is not configured; returning structured draft payload.",
            "title": clean_title,
            "content": clean_content,
        }
    return {
        "backend": normalized_backend,
        "stored": False,
        "status": "unsupported_backend",
    }


def _notion_configured() -> bool:
    return bool(_notion_api_token and _notion_database_id)


async def _capture_note_notion(*, title: str, content: str) -> tuple[dict[str, Any] | None, str | None]:
    if not _notion_configured():
        return None, "missing_config"
    payload = {
        "parent": {"database_id": _notion_database_id},
        "properties": {
            "title": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": title[:200]},
                    }
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": content[:2000]},
                        }
                    ]
                },
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {_notion_api_token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_webhook_timeout_sec, minimum=1.0, maximum=30.0))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.notion.com/v1/pages", headers=headers, json=payload) as resp:
                if resp.status in {200, 201}:
                    try:
                        body = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(body, dict):
                        return None, "invalid_json"
                    page_id = str(body.get("id", "")).strip()
                    url = str(body.get("url", "")).strip()
                    if not page_id:
                        return None, "invalid_json"
                    return {
                        "backend": "notion",
                        "stored": True,
                        "status": "created",
                        "page_id": page_id,
                        "url": url,
                    }, None
                if resp.status in {401, 403}:
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


def _as_str_list(value: Any, *, lower: bool = False, allow_none: bool = False) -> list[str] | None:
    if value is None:
        return None if allow_none else []
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if lower:
            cleaned = [item.lower() for item in cleaned]
        if cleaned:
            return cleaned
        return None if allow_none else []
    if isinstance(value, tuple):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if lower:
            cleaned = [item.lower() for item in cleaned]
        if cleaned:
            return cleaned
        return None if allow_none else []
    text = str(value).strip()
    if not text:
        return None if allow_none else []
    if lower:
        text = text.lower()
    return [text]


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


def _read_dead_letter_entries() -> list[dict[str, Any]]:
    path = _dead_letter_queue_path
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


def _write_dead_letter_entries(entries: list[dict[str, Any]]) -> None:
    path = _dead_letter_queue_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, default=str) for item in entries if isinstance(item, dict)]
    text = "\n".join(lines)
    if text:
        text += "\n"
    try:
        path.write_text(text)
    except OSError as exc:
        log.warning("Failed to write dead-letter queue: %s", exc)


def _append_dead_letter_entry(entry: dict[str, Any]) -> None:
    path = _dead_letter_queue_path
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str)
    try:
        with path.open("a") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        log.warning("Failed to append dead-letter queue entry: %s", exc)


def _dead_letter_matches(entry: dict[str, Any], *, status_filter: str) -> bool:
    status = str(entry.get("status", "pending")).strip().lower() or "pending"
    if status_filter == "all":
        return True
    if status_filter == "open":
        return status in {"pending", "failed"}
    return status == status_filter


def _dead_letter_queue_status(*, limit: int = 20, status_filter: str = "open") -> dict[str, Any]:
    entries = _read_dead_letter_entries()
    size = max(1, min(200, int(limit)))
    selected = [entry for entry in entries if _dead_letter_matches(entry, status_filter=status_filter)]
    recent_raw = selected[-size:]
    recent: list[dict[str, Any]] = []
    for entry in recent_raw:
        tool_name = str(entry.get("tool", "unknown")).strip().lower()
        args = entry.get("args")
        args_preview = _sanitize_inbound_payload(args if isinstance(args, dict) else {})
        recent.append(
            {
                "entry_id": str(entry.get("entry_id", "")),
                "timestamp": float(entry.get("timestamp", 0.0) or 0.0),
                "tool": tool_name,
                "status": str(entry.get("status", "pending")),
                "reason": str(entry.get("reason", "")),
                "attempts": int(entry.get("attempts", 0) or 0),
                "last_attempt_at": float(entry.get("last_attempt_at", 0.0) or 0.0),
                "last_error": str(entry.get("last_error", "")),
                "args_preview": args_preview,
                "replayable": tool_name in {
                    "webhook_trigger",
                    "slack_notify",
                    "discord_notify",
                    "email_send",
                    "pushover_notify",
                },
            }
        )
    pending = sum(1 for entry in entries if str(entry.get("status", "pending")).strip().lower() == "pending")
    failed = sum(1 for entry in entries if str(entry.get("status", "")).strip().lower() == "failed")
    replayed = sum(1 for entry in entries if str(entry.get("status", "")).strip().lower() == "replayed")
    return {
        "path": str(_dead_letter_queue_path),
        "exists": _dead_letter_queue_path.exists(),
        "entry_count": len(entries),
        "pending_count": pending,
        "failed_count": failed,
        "replayed_count": replayed,
        "recent": recent,
    }


def _dead_letter_enqueue(tool_name: str, args: dict[str, Any], *, reason: str, detail: str = "") -> str | None:
    if not isinstance(args, dict):
        return None
    if bool(args.get("_dead_letter_replay")):
        return None
    payload_args = {str(key): value for key, value in args.items() if str(key) != "_dead_letter_replay"}
    entry_id = secrets.token_hex(10)
    entry = {
        "timestamp": time.time(),
        "entry_id": entry_id,
        "tool": str(tool_name),
        "status": "pending",
        "reason": str(reason),
        "attempts": 0,
        "last_attempt_at": 0.0,
        "last_error": str(detail),
        "args": payload_args,
    }
    _append_dead_letter_entry(entry)
    _audit(
        "dead_letter_queue",
        {
            "result": "enqueued",
            "entry_id": entry_id,
            "tool": str(tool_name),
            "reason": str(reason),
        },
    )
    return entry_id


def _tool_response_text(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return ""
    first = content[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("text", "")).strip()


def _tool_response_success(text: str) -> bool:
    value = str(text).strip().lower()
    if not value:
        return False
    failure_markers = (
        "not permitted",
        "denied",
        "failed",
        "error",
        "timed out",
        "cancelled",
        "required",
        "missing",
        "not configured",
        "authentication failed",
        "invalid",
        "unexpected",
        "circuit breaker is open",
    )
    return not any(marker in value for marker in failure_markers)


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


async def _ha_request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    if _integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert _config is not None
    normalized_method = str(method).strip().upper() or "GET"
    url = f"{_config.hass_url}{path}"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec))
    headers = _ha_headers()
    if payload is not None:
        headers = {**headers, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                normalized_method,
                url,
                headers=headers,
                json=payload if payload is not None else None,
            ) as resp:
                if resp.status in {200, 201, 202, 204}:
                    if resp.status == 204:
                        _integration_record_success("home_assistant")
                        return {}, None
                    text = await resp.text()
                    if not text.strip():
                        _integration_record_success("home_assistant")
                        return {}, None
                    try:
                        body = json.loads(text)
                    except Exception:
                        return None, "invalid_json"
                    _integration_record_success("home_assistant")
                    return body, None
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
    _prune_guest_sessions()
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
        "trust_policy_count": len(_identity_trust_policies),
        "trust_policies": {domain: dict(policy) for domain, policy in sorted(_identity_trust_policies.items())},
        "guest_sessions_active": len(_guest_sessions),
        "guest_sessions": [
            {
                "guest_id": str(item.get("guest_id", "")),
                "expires_at": float(item.get("expires_at", 0.0) or 0.0),
                "capabilities": _as_str_list(item.get("capabilities"), lower=True),
            }
            for _, item in sorted(_guest_sessions.items(), key=lambda pair: str(pair[0]))
        ],
        "household_profile_count": len(_household_profiles),
        "household_profiles": {user: dict(row) for user, row in sorted(_household_profiles.items())},
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
            "voice_profile_user": "unknown",
            "voice_profile": {"verbosity": "normal", "confirmations": "standard", "pace": "normal", "tone": "auto"},
            "voice_profile_count": 0,
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
    snapshot.setdefault("voice_profile_user", "unknown")
    if not isinstance(snapshot.get("voice_profile"), dict):
        snapshot["voice_profile"] = {"verbosity": "normal", "confirmations": "standard", "pace": "normal", "tone": "auto"}
    else:
        profile = {str(key): value for key, value in snapshot["voice_profile"].items()}
        profile.setdefault("verbosity", "normal")
        profile.setdefault("confirmations", "standard")
        profile.setdefault("pace", "normal")
        profile.setdefault("tone", "auto")
        snapshot["voice_profile"] = profile
    snapshot.setdefault("voice_profile_count", 0)
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
            "latency_dashboards": {
                "sample_count": 0,
                "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                "by_intent": {},
                "by_tool_mix": {},
                "by_wake_mode": {},
            },
            "policy_decision_analytics": {
                "decision_count": 0,
                "by_tool": {},
                "by_status": {},
                "by_reason": {},
                "by_user": {},
                "by_user_tool": {},
            },
        }
    snapshot = {str(key): value for key, value in _runtime_observability_state.items()}
    if not isinstance(snapshot.get("intent_metrics"), dict):
        snapshot["intent_metrics"] = default_intent_metrics
    if not isinstance(snapshot.get("latency_dashboards"), dict):
        snapshot["latency_dashboards"] = {
            "sample_count": 0,
            "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "by_intent": {},
            "by_tool_mix": {},
            "by_wake_mode": {},
        }
    if not isinstance(snapshot.get("policy_decision_analytics"), dict):
        snapshot["policy_decision_analytics"] = {
            "decision_count": 0,
            "by_tool": {},
            "by_status": {},
            "by_reason": {},
            "by_user": {},
            "by_user_tool": {},
        }
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


def _expansion_snapshot() -> dict[str, Any]:
    _prune_guest_sessions()
    return {
        "proactive": {
            "pending_follow_through_count": len(_proactive_state.get("pending_follow_through", [])),
            "digest_snoozed_until": float(_proactive_state.get("digest_snoozed_until", 0.0) or 0.0),
            "last_briefing_at": float(_proactive_state.get("last_briefing_at", 0.0) or 0.0),
            "last_digest_at": float(_proactive_state.get("last_digest_at", 0.0) or 0.0),
        },
        "memory_governance": {
            "partition_overlay_count": len(_memory_partition_overlays),
            "last_quality_audit": dict(_memory_quality_last) if isinstance(_memory_quality_last, dict) else {},
        },
        "identity_trust": {
            "trust_policy_count": len(_identity_trust_policies),
            "guest_session_count": len(_guest_sessions),
            "household_profile_count": len(_household_profiles),
        },
        "home_orchestration": {
            "area_policy_count": len(_home_area_policies),
            "tracked_task_count": len(_home_task_runs),
            "automation_draft_count": len(_home_automation_drafts),
            "automation_applied_count": len(_home_automation_applied),
        },
        "skills_governance": {
            "quota_count": len(_skill_quotas),
            "sandbox_templates": sorted(SKILL_SANDBOX_TEMPLATES),
        },
        "planner_engine": {
            "task_graph_count": len(_planner_task_graphs),
            "deferred_action_count": len(_deferred_actions),
            "autonomy_task_count": sum(
                1
                for row in _deferred_actions.values()
                if isinstance(row, dict) and str(row.get("kind", "")).strip().lower() == "autonomy_task"
            ),
            "autonomy_waiting_checkpoint_count": sum(
                1
                for row in _deferred_actions.values()
                if isinstance(row, dict)
                and str(row.get("kind", "")).strip().lower() == "autonomy_task"
                and str(row.get("status", "")).strip().lower() == "waiting_checkpoint"
            ),
            "autonomy_last_cycle_at": (
                float(_autonomy_cycle_history[-1].get("timestamp", 0.0))
                if _autonomy_cycle_history
                else 0.0
            ),
        },
        "quality_evaluator": {
            "cached_report_count": len(_quality_reports),
            "recent_reports": _quality_reports_snapshot(limit=5),
        },
        "embodiment_presence": {
            "micro_expression_count": len(_micro_expression_library),
            "gaze_calibration_count": len(_gaze_calibrations),
            "gesture_profile_count": len(_gesture_envelopes),
            "privacy_posture": dict(_privacy_posture),
            "motion_safety_envelope": dict(_motion_safety_envelope),
        },
        "integration_hub": {
            "notes_backend_default": "local_markdown",
            "notes_dir": str(_notes_capture_dir),
            "release_channels": sorted(RELEASE_CHANNELS),
            "active_release_channel": str(_release_channel_state.get("active_channel", "dev")),
            "release_channel_config_path": str(_release_channel_config_path),
            "last_release_channel_check_at": float(_release_channel_state.get("last_check_at", 0.0) or 0.0),
            "last_release_channel_check_channel": str(_release_channel_state.get("last_check_channel", "")),
            "last_release_channel_check_passed": bool(_release_channel_state.get("last_check_passed", False)),
            "migration_checks": [
                _json_safe_clone(row)
                for row in (_release_channel_state.get("migration_checks") or [])
                if isinstance(row, dict)
            ][:20],
        },
    }


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






async def _calendar_fetch_events(
    *,
    calendar_entity_id: str | None,
    start_ts: float,
    end_ts: float,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    from jarvis.tools.services_domains.integrations import _calendar_fetch_events as _calendar_fetch_events_impl

    return await _calendar_fetch_events_impl(
        calendar_entity_id=calendar_entity_id,
        start_ts=start_ts,
        end_ts=end_ts,
    )


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


def _json_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _expansion_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    _persist_expansion_state()
    return _json_payload_response(payload)










def _home_plan_from_request(request_text: str) -> dict[str, Any]:
    text = str(request_text or "").strip().lower()
    if "movie" in text:
        return {
            "label": "movie_mode",
            "steps": [
                {"domain": "light", "action": "turn_off", "entity_id": "light.main_room"},
                {"domain": "light", "action": "turn_on", "entity_id": "light.bias_backlight", "data": {"brightness": 80}},
                {"domain": "media_player", "action": "media_play", "entity_id": "media_player.living_room_tv"},
            ],
        }
    if "bedtime" in text:
        return {
            "label": "bedtime_routine",
            "steps": [
                {"domain": "lock", "action": "lock", "entity_id": "lock.front_door"},
                {"domain": "light", "action": "turn_off", "entity_id": "light.downstairs"},
                {"domain": "climate", "action": "set_temperature", "entity_id": "climate.main", "data": {"temperature": 68}},
            ],
        }
    return {
        "label": "custom",
        "steps": [],
    }


def _slugify_identifier(value: str, *, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or fallback


def _json_preview(value: Any, *, limit: int = 500) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _structured_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    prev = previous if isinstance(previous, dict) else {}
    curr = current if isinstance(current, dict) else {}
    added = sorted(key for key in curr.keys() if key not in prev)
    removed = sorted(key for key in prev.keys() if key not in curr)
    changed = sorted(
        key
        for key in curr.keys()
        if key in prev and _json_preview(prev.get(key)) != _json_preview(curr.get(key))
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "has_changes": bool(added or removed or changed),
        "previous_preview": _json_preview(prev),
        "current_preview": _json_preview(curr),
    }


def _normalize_automation_config(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    alias = str(args.get("alias", "")).strip()
    if not alias:
        return None, "alias is required."
    trigger = args.get("trigger") if isinstance(args.get("trigger"), dict) else {}
    conditions = args.get("condition") if isinstance(args.get("condition"), list) else []
    actions = args.get("actions") if isinstance(args.get("actions"), list) else []
    if not trigger:
        return None, "trigger object is required."
    if not actions:
        return None, "actions list is required."
    normalized_actions = [dict(row) for row in actions if isinstance(row, dict)]
    if not normalized_actions:
        return None, "actions list must contain object entries."
    return {
        "alias": alias,
        "trigger": dict(trigger),
        "condition": [dict(row) for row in conditions if isinstance(row, dict)],
        "action": normalized_actions,
        "mode": str(args.get("mode", "single")).strip().lower() or "single",
    }, ""


def _automation_entry_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_id": str(draft.get("draft_id", "")),
        "automation_id": str(draft.get("automation_id", "")),
        "alias": str(draft.get("alias", "")),
        "status": str(draft.get("status", "draft")),
        "updated_at": float(draft.get("updated_at", 0.0) or 0.0),
    }


async def _apply_ha_automation_config(automation_id: str, config_payload: dict[str, Any]) -> tuple[bool, str]:
    if not _config or not _config.has_home_assistant:
        return False, "missing_config"
    path = f"/api/config/automation/config/{automation_id}"
    _, error_code = await _ha_request_json("PUT", path, payload=config_payload)
    if error_code in {"http_error", "not_found"}:
        _, error_code = await _ha_request_json("POST", path, payload=config_payload)
    if error_code is not None:
        return False, error_code
    _, reload_error = await _ha_call_service("automation", "reload", {})
    if reload_error is not None:
        return False, reload_error
    return True, ""


async def _delete_ha_automation_config(automation_id: str) -> tuple[bool, str]:
    if not _config or not _config.has_home_assistant:
        return False, "missing_config"
    path = f"/api/config/automation/config/{automation_id}"
    _, error_code = await _ha_request_json("DELETE", path)
    if error_code is not None:
        return False, error_code
    _, reload_error = await _ha_call_service("automation", "reload", {})
    if reload_error is not None:
        return False, reload_error
    return True, ""


def _autonomy_tasks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _deferred_actions.values():
        if not isinstance(row, dict):
            continue
        if str(row.get("kind", "")).strip().lower() != "autonomy_task":
            continue
        rows.append(row)
    return rows





def _planner_ready_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, list):
        return []
    status_by_id = {
        str(node.get("id", "")): str(node.get("status", "pending")).strip().lower()
        for node in nodes
        if isinstance(node, dict)
    }
    ready: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("status", "pending")).strip().lower() != "pending":
            continue
        deps = _as_str_list(node.get("depends_on"), lower=False)
        if all(status_by_id.get(dep, "done") == "done" for dep in deps):
            ready.append(dict(node))
    return ready










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

dead_letter_list_tool = tool(
    "dead_letter_list",
    "List dead-letter queue entries for failed outbound notifications/webhooks.",
    SERVICE_TOOL_SCHEMAS["dead_letter_list"],
)(dead_letter_list)

dead_letter_replay_tool = tool(
    "dead_letter_replay",
    "Replay failed outbound dead-letter entries by id or filter.",
    SERVICE_TOOL_SCHEMAS["dead_letter_replay"],
)(dead_letter_replay)

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

proactive_assistant_tool = tool(
    "proactive_assistant",
    "Run proactive briefing/anomaly/digest workflows and follow-through queueing.",
    SERVICE_TOOL_SCHEMAS["proactive_assistant"],
)(proactive_assistant)

memory_governance_tool = tool(
    "memory_governance",
    "Manage per-user memory overlays and run memory quality audits/cleanup.",
    SERVICE_TOOL_SCHEMAS["memory_governance"],
)(memory_governance)

identity_trust_tool = tool(
    "identity_trust",
    "Manage identity confidence, trust policies, guest mode sessions, and household profiles.",
    SERVICE_TOOL_SCHEMAS["identity_trust"],
)(identity_trust)

home_orchestrator_tool = tool(
    "home_orchestrator",
    "Create and execute multi-entity home plans with area policy checks and task tracking.",
    SERVICE_TOOL_SCHEMAS["home_orchestrator"],
)(home_orchestrator)

skills_governance_tool = tool(
    "skills_governance",
    "Negotiate skills, inspect dependency health, enforce quotas, and run skill harness checks.",
    SERVICE_TOOL_SCHEMAS["skills_governance"],
)(skills_governance)

planner_engine_tool = tool(
    "planner_engine",
    "Planner/executor split with task graphs, checkpoint/resume, deferred scheduling, and self-critique.",
    SERVICE_TOOL_SCHEMAS["planner_engine"],
)(planner_engine)

quality_evaluator_tool = tool(
    "quality_evaluator",
    "Generate weekly quality artifacts and run deterministic evaluation datasets.",
    SERVICE_TOOL_SCHEMAS["quality_evaluator"],
)(quality_evaluator)

embodiment_presence_tool = tool(
    "embodiment_presence",
    "Manage micro-expressions, gaze calibration, gesture envelopes, privacy posture, and motion safety envelopes.",
    SERVICE_TOOL_SCHEMAS["embodiment_presence"],
)(embodiment_presence)

integration_hub_tool = tool(
    "integration_hub",
    "Run calendar/notes/messaging/commute/shopping/research orchestration workflows and release-channel operations.",
    SERVICE_TOOL_SCHEMAS["integration_hub"],
)(integration_hub)

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
            dead_letter_list_tool,
            dead_letter_replay_tool,
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
            proactive_assistant_tool,
            memory_governance_tool,
            identity_trust_tool,
            home_orchestrator_tool,
            skills_governance_tool,
            planner_engine_tool,
            quality_evaluator_tool,
            embodiment_presence_tool,
            integration_hub_tool,
        ],
    )
