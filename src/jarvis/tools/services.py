"""External service tools: smart home, weather, etc.

All destructive actions require confirmation (dry-run by default).
Everything is audit-logged.
"""

from __future__ import annotations

import asyncio  # noqa: F401
import hashlib  # noqa: F401  # accessed by domain modules via services module alias
import hmac  # noqa: F401  # accessed by domain modules via services module alias
import json  # noqa: F401  # accessed by domain modules via services module alias
import logging
import math
import random
import re
import smtplib
import sys
import time
from contextlib import suppress  # noqa: F401  # accessed by domain modules via services module alias
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp  # noqa: F401

from jarvis.config import Config
from jarvis.skills import SkillRegistry
from jarvis.tool_policy import is_tool_allowed
from jarvis.tool_summary import record_summary, list_summaries  # noqa: F401  # accessed via services module alias
from jarvis.memory import MemoryEntry, MemoryStore
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES, normalize_service_error_code
from jarvis.tools.service_policy import (
    SENSITIVE_DOMAINS,  # noqa: F401  # compatibility export for domain modules
    HA_MUTATING_ALLOWED_ACTIONS,
    INTEGRATION_TOOL_MAP,  # noqa: F401  # accessed by runtime module via services alias
    SAFE_MODE_BLOCKED_TOOLS,
    SENSITIVE_AUDIT_KEY_TOKENS,  # noqa: F401  # accessed by runtime module via services alias
    INBOUND_REDACT_HEADER_TOKENS,  # noqa: F401  # accessed by runtime module via services alias
    INBOUND_MAX_STRING_CHARS,  # noqa: F401  # accessed by runtime module via services alias
    INBOUND_MAX_COLLECTION_ITEMS,  # noqa: F401  # accessed by runtime module via services alias
    AUDIT_REDACTED,  # noqa: F401  # accessed by runtime module via services alias
    AMBIGUOUS_REFERENCE_TERMS,  # noqa: F401  # accessed by runtime module via services alias
    HIGH_RISK_INTENT_TERMS,  # noqa: F401  # accessed by runtime module via services alias
    EXPLICIT_TARGET_TERMS,  # noqa: F401  # accessed by runtime module via services alias
    AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS,  # noqa: F401  # accessed by runtime module via services alias
    MEMORY_SCOPE_TAG_PREFIX,  # noqa: F401  # accessed by runtime module via services alias
    MEMORY_SCOPES,  # noqa: F401  # accessed by runtime module via services alias
    MEMORY_QUERY_SCOPE_HINTS,  # noqa: F401  # accessed by runtime module via services alias
    AUDIT_REASON_MESSAGES,  # noqa: F401  # accessed by runtime module via services alias
)
from jarvis.tools.service_schemas import (
    SERVICE_RUNTIME_REQUIRED_FIELDS,  # noqa: F401  # compatibility export for tests/importers
    SERVICE_TOOL_SCHEMAS,  # noqa: F401  # compatibility export for tests/importers
)
from jarvis.tools.services_server import create_services_server  # noqa: F401  # compatibility export for callers
from jarvis.tools.services_runtime_state import (
    bind_runtime_state as _runtime_bind_runtime_state,
    expansion_state_payload as _runtime_expansion_state_payload,
    load_expansion_state as _runtime_load_expansion_state,
    persist_expansion_state as _runtime_persist_expansion_state,
    replace_state_dict as _runtime_replace_state_dict,
)
from jarvis.tools.services_integrations_runtime import (
    capture_note as _runtime_capture_note,
    capture_note_notion as _runtime_capture_note_notion,
    evaluate_release_channel as _runtime_evaluate_release_channel,
    load_release_channel_config as _runtime_load_release_channel_config,
    notion_configured as _runtime_notion_configured,
    run_release_channel_check as _runtime_run_release_channel_check,
    write_quality_report_artifact as _runtime_write_quality_report_artifact,
)
from jarvis.tools.services_identity_runtime import (
    identity_audit_fields as _runtime_identity_audit_fields,
    identity_authorize as _runtime_identity_authorize,
    identity_context as _runtime_identity_context,
    identity_enriched_audit as _runtime_identity_enriched_audit,
    identity_trust_domain as _runtime_identity_trust_domain,
)
from jarvis.tools.services_status_runtime import (
    duration_p95_ms as _runtime_duration_p95_ms,
    expansion_snapshot as _runtime_expansion_snapshot,
    health_rollup as _runtime_health_rollup,
    identity_status_snapshot as _runtime_identity_status_snapshot,
    integration_health_snapshot as _runtime_integration_health_snapshot,
    jarvis_scorecard_snapshot as _runtime_jarvis_scorecard_snapshot,
    observability_snapshot as _runtime_observability_snapshot,
    recent_tool_rows as _runtime_recent_tool_rows,
    score_label as _runtime_score_label,
    voice_attention_snapshot as _runtime_voice_attention_snapshot,
)
from jarvis.tools.services_ha_runtime import (
    ha_call_service as _runtime_ha_call_service,
    ha_get_domain_services as _runtime_ha_get_domain_services,
    ha_get_json as _runtime_ha_get_json,
    ha_get_state as _runtime_ha_get_state,
    ha_render_template as _runtime_ha_render_template,
    ha_request_json as _runtime_ha_request_json,
)
from jarvis.tools.services_recovery_runtime import (
    RecoveryOperation as _runtime_RecoveryOperation,
    append_dead_letter_entry as _runtime_append_dead_letter_entry,
    dead_letter_enqueue as _runtime_dead_letter_enqueue,
    dead_letter_matches as _runtime_dead_letter_matches,
    dead_letter_queue_status as _runtime_dead_letter_queue_status,
    read_dead_letter_entries as _runtime_read_dead_letter_entries,
    read_recovery_journal_entries as _runtime_read_recovery_journal_entries,
    recovery_begin as _runtime_recovery_begin,
    recovery_finish as _runtime_recovery_finish,
    recovery_journal_status as _runtime_recovery_journal_status,
    recovery_reconcile_interrupted as _runtime_recovery_reconcile_interrupted,
    tool_response_success as _runtime_tool_response_success,
    tool_response_text as _runtime_tool_response_text,
    write_dead_letter_entries as _runtime_write_dead_letter_entries,
    write_recovery_journal_entry as _runtime_write_recovery_journal_entry,
)
from jarvis.tools.services_audit_runtime import (
    apply_retention_policies as _runtime_apply_retention_policies,
    audit as _runtime_audit,
    audit_decision_explanation as _runtime_audit_decision_explanation,
    audit_outcome as _runtime_audit_outcome,
    audit_reason_code as _runtime_audit_reason_code,
    audit_status as _runtime_audit_status,
    configure_audit_encryption as _runtime_configure_audit_encryption,
    contains_pii as _runtime_contains_pii,
    decode_audit_line as _runtime_decode_audit_line,
    encrypt_audit_line as _runtime_encrypt_audit_line,
    humanize_chain_token as _runtime_humanize_chain_token,
    metadata_only_audit_details as _runtime_metadata_only_audit_details,
    prune_audit_file as _runtime_prune_audit_file,
    redact_sensitive_for_audit as _runtime_redact_sensitive_for_audit,
    rotate_audit_log_if_needed as _runtime_rotate_audit_log_if_needed,
    sanitize_inbound_headers as _runtime_sanitize_inbound_headers,
    sanitize_inbound_payload as _runtime_sanitize_inbound_payload,
)
from jarvis.tools.services_schedule_runtime import (
    allocate_reminder_id as _runtime_allocate_reminder_id,
    allocate_timer_id as _runtime_allocate_timer_id,
    duration_seconds as _runtime_duration_seconds,
    format_duration as _runtime_format_duration,
    load_reminders_from_store as _runtime_load_reminders_from_store,
    load_timers_from_store as _runtime_load_timers_from_store,
    local_timezone as _runtime_local_timezone,
    parse_datetime_text as _runtime_parse_datetime_text,
    parse_due_timestamp as _runtime_parse_due_timestamp,
    prune_timers as _runtime_prune_timers,
    reminder_status as _runtime_reminder_status,
    timer_status as _runtime_timer_status,
    timestamp_to_iso_utc as _runtime_timestamp_to_iso_utc,
)
from jarvis.tools.services_memory_runtime import (
    expansion_payload_response as _runtime_expansion_payload_response,
    infer_memory_scope as _runtime_infer_memory_scope,
    json_payload_response as _runtime_json_payload_response,
    memory_confidence_label as _runtime_memory_confidence_label,
    memory_confidence_score as _runtime_memory_confidence_score,
    memory_entry_scope as _runtime_memory_entry_scope,
    memory_policy_scopes_for_query as _runtime_memory_policy_scopes_for_query,
    memory_requested_scopes as _runtime_memory_requested_scopes,
    memory_scope_for_add as _runtime_memory_scope_for_add,
    memory_scope_from_tags as _runtime_memory_scope_from_tags,
    memory_scope_tag as _runtime_memory_scope_tag,
    memory_scope_tags as _runtime_memory_scope_tags,
    memory_source_trail as _runtime_memory_source_trail,
    memory_visible_tags as _runtime_memory_visible_tags,
    normalize_memory_scope as _runtime_normalize_memory_scope,
)
from jarvis.tools.services_preview_runtime import (
    consume_plan_preview_token as _runtime_consume_plan_preview_token,
    is_ambiguous_entity_target as _runtime_is_ambiguous_entity_target,
    is_ambiguous_high_risk_text as _runtime_is_ambiguous_high_risk_text,
    issue_plan_preview_token as _runtime_issue_plan_preview_token,
    plan_preview_message as _runtime_plan_preview_message,
    plan_preview_signature as _runtime_plan_preview_signature,
    preview_gate as _runtime_preview_gate,
    prune_plan_previews as _runtime_prune_plan_previews,
    tokenized_words as _runtime_tokenized_words,
)
from jarvis.tools.services_circuit_runtime import (
    ensure_circuit_breaker_state as _runtime_ensure_circuit_breaker_state,
    integration_circuit_open as _runtime_integration_circuit_open,
    integration_circuit_open_message as _runtime_integration_circuit_open_message,
    integration_circuit_snapshot as _runtime_integration_circuit_snapshot,
    integration_for_tool as _runtime_integration_for_tool,
    integration_record_failure as _runtime_integration_record_failure,
    integration_record_success as _runtime_integration_record_success,
)
from jarvis.tools.services_policy_runtime import (
    hhmm_to_minutes as _runtime_hhmm_to_minutes,
    identity_profile_level as _runtime_identity_profile_level,
    normalize_nudge_policy as _runtime_normalize_nudge_policy,
    profile_rank as _runtime_profile_rank,
    prune_guest_sessions as _runtime_prune_guest_sessions,
    quiet_window_active as _runtime_quiet_window_active,
    register_guest_session as _runtime_register_guest_session,
    resolve_guest_session as _runtime_resolve_guest_session,
)
from jarvis.tools.services_automation_runtime import (
    apply_ha_automation_config as _runtime_apply_ha_automation_config,
    automation_entry_from_draft as _runtime_automation_entry_from_draft,
    autonomy_tasks as _runtime_autonomy_tasks,
    delete_ha_automation_config as _runtime_delete_ha_automation_config,
    home_plan_from_request as _runtime_home_plan_from_request,
    json_preview as _runtime_json_preview,
    normalize_automation_config as _runtime_normalize_automation_config,
    planner_ready_nodes as _runtime_planner_ready_nodes,
    slugify_identifier as _runtime_slugify_identifier,
    structured_diff as _runtime_structured_diff,
)
from jarvis.tools.services_domains.home import (  # noqa: F401  # compatibility exports for tests/importers
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
from jarvis.tools.services_domains.planner import (  # noqa: F401  # compatibility exports for tests/importers
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
from jarvis.tools.services_domains.integrations import (  # noqa: F401  # compatibility exports for tests/importers
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
from jarvis.tools.services_domains.comms import (  # noqa: F401  # compatibility exports for tests/importers
    slack_notify,
    discord_notify,
    email_send,
    email_summary,
    todoist_add_task,
    todoist_list_tasks,
    pushover_notify,
)
from jarvis.tools.services_domains.governance import (  # noqa: F401  # compatibility exports for tests/importers
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
from jarvis.tools.services_domains.trust import (  # noqa: F401  # compatibility exports for tests/importers
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

ACTION_COOLDOWN_SEC = 2.0
ACTION_HISTORY_RETENTION_SEC = 3600.0
ACTION_HISTORY_MAX_ENTRIES = 2000
HA_STATE_CACHE_TTL_SEC = 2.0
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
# Backward compatibility for existing imports/tests.
SERVICE_ERROR_CODES = TOOL_SERVICE_ERROR_CODES


def _services_module() -> Any:
    return sys.modules[__name__]


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
    _runtime_bind_runtime_state(_services_module(), config, memory_store)


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
    _runtime_configure_audit_encryption(_services_module(), enabled=enabled, key=key)


def _encrypt_audit_line(payload: dict[str, Any]) -> str:
    return _runtime_encrypt_audit_line(_services_module(), payload)


def _decode_audit_line(line: str) -> dict[str, Any] | None:
    return _runtime_decode_audit_line(_services_module(), line)


def decode_audit_entry_line(line: str) -> dict[str, Any] | None:
    return _decode_audit_line(line)


def _audit_outcome(details: dict[str, Any]) -> str:
    return _runtime_audit_outcome(details)


def _audit_reason_code(details: dict[str, Any]) -> str:
    return _runtime_audit_reason_code(details)


def _humanize_chain_token(token: str) -> str:
    return _runtime_humanize_chain_token(token)


def _audit_decision_explanation(action: str, details: dict[str, Any]) -> str:
    return _runtime_audit_decision_explanation(_services_module(), action, details)


def _audit(action: str, details: dict) -> None:
    _runtime_audit(_services_module(), action, details)


def _rotate_audit_log_if_needed() -> None:
    _runtime_rotate_audit_log_if_needed(_services_module())


def _redact_sensitive_for_audit(value: Any, *, key_hint: str | None = None) -> Any:
    return _runtime_redact_sensitive_for_audit(_services_module(), value, key_hint=key_hint)


def _metadata_only_audit_details(action: str, details: dict[str, Any]) -> dict[str, Any]:
    return _runtime_metadata_only_audit_details(_services_module(), action, details)


def _sanitize_inbound_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    return _runtime_sanitize_inbound_headers(_services_module(), headers)


def _sanitize_inbound_payload(value: Any, *, key_hint: str | None = None, depth: int = 0) -> Any:
    return _runtime_sanitize_inbound_payload(
        _services_module(),
        value,
        key_hint=key_hint,
        depth=depth,
    )


def _contains_pii(text: str) -> bool:
    return _runtime_contains_pii(_services_module(), text)


def _identity_context(args: dict[str, Any] | None) -> dict[str, Any]:
    return _runtime_identity_context(_services_module(), args)


def _identity_audit_fields(context: dict[str, Any], decision_chain: list[str] | None = None) -> dict[str, Any]:
    return _runtime_identity_audit_fields(_services_module(), context, decision_chain)


def _identity_trust_domain(tool_name: str, args: dict[str, Any] | None) -> str:
    return _runtime_identity_trust_domain(_services_module(), tool_name, args)


def _identity_authorize(
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


def _identity_enriched_audit(details: dict[str, Any], identity: dict[str, Any], decision_chain: list[str]) -> dict[str, Any]:
    return _runtime_identity_enriched_audit(
        _services_module(),
        details,
        identity,
        decision_chain,
    )


def _tokenized_words(text: str) -> list[str]:
    return _runtime_tokenized_words(text)


def _is_ambiguous_high_risk_text(text: str) -> bool:
    return _runtime_is_ambiguous_high_risk_text(_services_module(), text)


def _is_ambiguous_entity_target(entity_id: str) -> bool:
    return _runtime_is_ambiguous_entity_target(entity_id)


def _plan_preview_signature(tool_name: str, payload: dict[str, Any]) -> str:
    return _runtime_plan_preview_signature(tool_name, payload)


def _prune_plan_previews(now_ts: float | None = None) -> None:
    _runtime_prune_plan_previews(_services_module(), now_ts=now_ts)


def _issue_plan_preview_token(tool_name: str, signature: str, risk: str, summary: str) -> str:
    return _runtime_issue_plan_preview_token(_services_module(), tool_name, signature, risk, summary)


def _consume_plan_preview_token(token: str, *, tool_name: str, signature: str) -> bool:
    return _runtime_consume_plan_preview_token(_services_module(), token, tool_name=tool_name, signature=signature)


def _plan_preview_message(*, summary: str, risk: str, token: str, ttl_sec: float = PLAN_PREVIEW_TTL_SEC) -> str:
    return _runtime_plan_preview_message(summary=summary, risk=risk, token=token, ttl_sec=ttl_sec)


def _preview_gate(
    *,
    tool_name: str,
    args: dict[str, Any],
    risk: str,
    summary: str,
    signature_payload: dict[str, Any],
    enforce_default: bool,
) -> str | None:
    return _runtime_preview_gate(
        _services_module(),
        tool_name=tool_name,
        args=args,
        risk=risk,
        summary=summary,
        signature_payload=signature_payload,
        enforce_default=enforce_default,
    )


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
    return _runtime_integration_for_tool(_services_module(), tool_name)


def _ensure_circuit_breaker_state(integration: str) -> dict[str, Any]:
    return _runtime_ensure_circuit_breaker_state(_services_module(), integration)


def _integration_circuit_open(integration: str, *, now_ts: float | None = None) -> tuple[bool, float]:
    return _runtime_integration_circuit_open(_services_module(), integration, now_ts=now_ts)


def _integration_record_failure(integration: str, error_code: str) -> None:
    _runtime_integration_record_failure(_services_module(), integration, error_code)


def _integration_record_success(integration: str) -> None:
    _runtime_integration_record_success(_services_module(), integration)


def _integration_circuit_snapshot(integration: str, *, now_ts: float | None = None) -> dict[str, Any]:
    return _runtime_integration_circuit_snapshot(_services_module(), integration, now_ts=now_ts)


def _integration_circuit_open_message(integration: str, remaining_sec: float) -> str:
    return _runtime_integration_circuit_open_message(integration, remaining_sec)


def _normalize_nudge_policy(value: Any) -> str:
    return _runtime_normalize_nudge_policy(value)


def _hhmm_to_minutes(value: str) -> int | None:
    return _runtime_hhmm_to_minutes(value)


def _quiet_window_active(*, now_ts: float | None = None) -> bool:
    return _runtime_quiet_window_active(_services_module(), now_ts=now_ts)


def _identity_profile_level(profile: str) -> str:
    return _runtime_identity_profile_level(profile)


def _profile_rank(profile: str) -> int:
    return _runtime_profile_rank(profile)


def _prune_guest_sessions(*, now_ts: float | None = None) -> None:
    _runtime_prune_guest_sessions(_services_module(), now_ts=now_ts)


def _resolve_guest_session(token: str, *, now_ts: float | None = None) -> dict[str, Any] | None:
    return _runtime_resolve_guest_session(_services_module(), token, now_ts=now_ts)


def _register_guest_session(
    *,
    guest_id: str,
    capabilities: list[str],
    ttl_sec: float,
    now_ts: float | None = None,
) -> dict[str, Any]:
    return _runtime_register_guest_session(
        _services_module(),
        guest_id=guest_id,
        capabilities=capabilities,
        ttl_sec=ttl_sec,
        now_ts=now_ts,
    )


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
    _runtime_replace_state_dict(_services_module(), target, source)


def _expansion_state_payload() -> dict[str, Any]:
    return _runtime_expansion_state_payload(_services_module())


def _persist_expansion_state() -> None:
    _runtime_persist_expansion_state(_services_module())


def _load_expansion_state() -> None:
    _runtime_load_expansion_state(_services_module())


def _run_release_channel_check(base: Path, check: dict[str, Any]) -> dict[str, Any]:
    return _runtime_run_release_channel_check(base, check)


def _load_release_channel_config() -> tuple[dict[str, Any] | None, str]:
    return _runtime_load_release_channel_config(_services_module())


def _evaluate_release_channel(*, channel: str, workspace: Path | None = None) -> dict[str, Any]:
    return _runtime_evaluate_release_channel(
        _services_module(),
        channel=channel,
        workspace=workspace,
    )


def _write_quality_report_artifact(payload: dict[str, Any], *, report_path: str | None = None) -> str:
    return _runtime_write_quality_report_artifact(
        _services_module(),
        payload,
        report_path=report_path,
    )


def _capture_note(*, backend: str, title: str, content: str, path_hint: str = "") -> dict[str, Any]:
    return _runtime_capture_note(
        _services_module(),
        backend=backend,
        title=title,
        content=content,
        path_hint=path_hint,
    )


def _notion_configured() -> bool:
    return _runtime_notion_configured(_services_module())


async def _capture_note_notion(*, title: str, content: str) -> tuple[dict[str, Any] | None, str | None]:
    return await _runtime_capture_note_notion(
        _services_module(),
        title=title,
        content=content,
    )


def _duration_seconds(value: Any) -> float | None:
    return _runtime_duration_seconds(_services_module(), value)


def _local_timezone():
    return _runtime_local_timezone()


def _parse_datetime_text(value: str) -> datetime | None:
    return _runtime_parse_datetime_text(value)


def _parse_due_timestamp(value: Any, *, now_ts: float | None = None) -> float | None:
    return _runtime_parse_due_timestamp(_services_module(), value, now_ts=now_ts)


def _timestamp_to_iso_utc(ts: float) -> str:
    return _runtime_timestamp_to_iso_utc(ts)


def _format_duration(seconds: float) -> str:
    return _runtime_format_duration(seconds)


def _allocate_timer_id() -> int:
    return _runtime_allocate_timer_id(_services_module())


def _allocate_reminder_id() -> int:
    return _runtime_allocate_reminder_id(_services_module())


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
    return _runtime_audit_status(_services_module())


def _read_recovery_journal_entries() -> list[dict[str, Any]]:
    return _runtime_read_recovery_journal_entries(_services_module())


def _write_recovery_journal_entry(payload: dict[str, Any]) -> None:
    _runtime_write_recovery_journal_entry(_services_module(), payload)


def _recovery_begin(tool_name: str, *, operation: str, context: dict[str, Any] | None = None) -> str:
    return _runtime_recovery_begin(
        _services_module(),
        tool_name,
        operation=operation,
        context=context,
    )


def _recovery_finish(
    entry_id: str,
    *,
    tool_name: str,
    operation: str,
    status: str,
    detail: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    _runtime_recovery_finish(
        _services_module(),
        entry_id,
        tool_name=tool_name,
        operation=operation,
        status=status,
        detail=detail,
        context=context,
    )


class _RecoveryOperation(_runtime_RecoveryOperation):
    def __init__(self, tool_name: str, *, operation: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            _services_module(),
            tool_name,
            operation=operation,
            context=context,
        )


def _recovery_operation(
    tool_name: str,
    *,
    operation: str,
    context: dict[str, Any] | None = None,
) -> _RecoveryOperation:
    return _RecoveryOperation(tool_name, operation=operation, context=context)


def _recovery_reconcile_interrupted() -> None:
    _runtime_recovery_reconcile_interrupted(_services_module())


def _recovery_journal_status(*, limit: int = 20) -> dict[str, Any]:
    return _runtime_recovery_journal_status(_services_module(), limit=limit)


def _read_dead_letter_entries() -> list[dict[str, Any]]:
    return _runtime_read_dead_letter_entries(_services_module())


def _write_dead_letter_entries(entries: list[dict[str, Any]]) -> None:
    _runtime_write_dead_letter_entries(_services_module(), entries)


def _append_dead_letter_entry(entry: dict[str, Any]) -> None:
    _runtime_append_dead_letter_entry(_services_module(), entry)


def _dead_letter_matches(entry: dict[str, Any], *, status_filter: str) -> bool:
    return _runtime_dead_letter_matches(entry, status_filter=status_filter)


def _dead_letter_queue_status(*, limit: int = 20, status_filter: str = "open") -> dict[str, Any]:
    return _runtime_dead_letter_queue_status(
        _services_module(),
        limit=limit,
        status_filter=status_filter,
    )


def _dead_letter_enqueue(tool_name: str, args: dict[str, Any], *, reason: str, detail: str = "") -> str | None:
    return _runtime_dead_letter_enqueue(
        _services_module(),
        tool_name,
        args,
        reason=reason,
        detail=detail,
    )


def _tool_response_text(result: dict[str, Any]) -> str:
    return _runtime_tool_response_text(result)


def _tool_response_success(text: str) -> bool:
    return _runtime_tool_response_success(text)


def _prune_audit_file(path: Path, *, cutoff_ts: float) -> int:
    return _runtime_prune_audit_file(_services_module(), path, cutoff_ts=cutoff_ts)


def _apply_retention_policies() -> None:
    _runtime_apply_retention_policies(_services_module())


def _prune_timers(now_mono: float | None = None) -> None:
    _runtime_prune_timers(_services_module(), now_mono=now_mono)


def _timer_status() -> dict[str, Any]:
    return _runtime_timer_status(_services_module())


def _load_timers_from_store() -> None:
    _runtime_load_timers_from_store(_services_module())


def _reminder_status() -> dict[str, Any]:
    return _runtime_reminder_status(_services_module())


def _load_reminders_from_store() -> None:
    _runtime_load_reminders_from_store(_services_module())


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
    return await _runtime_ha_get_state(_services_module(), entity_id)


async def _ha_get_domain_services(domain: str) -> tuple[list[str] | None, str | None]:
    return await _runtime_ha_get_domain_services(_services_module(), domain)


async def _ha_call_service(
    domain: str,
    service: str,
    service_data: dict[str, Any],
    *,
    return_response: bool = False,
    timeout_sec: float = 10.0,
) -> tuple[list[Any] | None, str | None]:
    return await _runtime_ha_call_service(
        _services_module(),
        domain,
        service,
        service_data,
        return_response=return_response,
        timeout_sec=timeout_sec,
    )


async def _ha_get_json(
    path: str,
    *,
    params: dict[str, str] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    return await _runtime_ha_get_json(
        _services_module(),
        path,
        params=params,
        timeout_sec=timeout_sec,
    )


async def _ha_request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    return await _runtime_ha_request_json(
        _services_module(),
        method,
        path,
        payload=payload,
        timeout_sec=timeout_sec,
    )


async def _ha_render_template(template_text: str, *, timeout_sec: float = 10.0) -> tuple[str | None, str | None]:
    return await _runtime_ha_render_template(_services_module(), template_text, timeout_sec=timeout_sec)


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
    return _runtime_integration_health_snapshot(_services_module())


def _identity_status_snapshot() -> dict[str, Any]:
    return _runtime_identity_status_snapshot(_services_module())


def _voice_attention_snapshot() -> dict[str, Any]:
    return _runtime_voice_attention_snapshot(_services_module())


def _observability_snapshot() -> dict[str, Any]:
    return _runtime_observability_snapshot(_services_module())


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
    return _runtime_expansion_snapshot(_services_module())


def _health_rollup(
    *,
    config_present: bool,
    memory_state: dict[str, Any] | None,
    recent_tools: list[dict[str, object]] | dict[str, str],
    identity_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _runtime_health_rollup(
        config_present=config_present,
        memory_state=memory_state,
        recent_tools=recent_tools,
        identity_status=identity_status,
    )


def _score_label(score: float) -> str:
    return _runtime_score_label(_services_module(), score)


def _recent_tool_rows(recent_tools: list[dict[str, object]] | dict[str, str] | Any) -> list[dict[str, object]]:
    return _runtime_recent_tool_rows(recent_tools)


def _duration_p95_ms(rows: list[dict[str, object]]) -> float:
    return _runtime_duration_p95_ms(rows)


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
    return _runtime_jarvis_scorecard_snapshot(
        _services_module(),
        recent_tools=recent_tools,
        health=health,
        observability=observability,
        identity=identity,
        tool_policy=tool_policy,
        audit=audit,
        integrations=integrations,
    )


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
    return _runtime_normalize_memory_scope(_services_module(), value)


def _memory_scope_tag(scope: str) -> str:
    return _runtime_memory_scope_tag(_services_module(), scope)


def _memory_scope_from_tags(tags: list[str] | None) -> str | None:
    return _runtime_memory_scope_from_tags(_services_module(), tags)


def _infer_memory_scope(*, kind: str, source: str) -> str:
    return _runtime_infer_memory_scope(kind=kind, source=source)


def _memory_scope_for_add(*, kind: str, source: str, tags: list[str], requested_scope: Any) -> str:
    return _runtime_memory_scope_for_add(
        _services_module(),
        kind=kind,
        source=source,
        tags=tags,
        requested_scope=requested_scope,
    )


def _memory_scope_tags(tags: list[str], scope: str) -> list[str]:
    return _runtime_memory_scope_tags(_services_module(), tags, scope)


def _memory_visible_tags(tags: list[str]) -> list[str]:
    return _runtime_memory_visible_tags(_services_module(), tags)


def _memory_entry_scope(entry: MemoryEntry) -> str:
    return _runtime_memory_entry_scope(_services_module(), entry)


def _memory_policy_scopes_for_query(query: str) -> list[str]:
    return _runtime_memory_policy_scopes_for_query(_services_module(), query)


def _memory_requested_scopes(scopes_value: Any, *, query: str = "") -> list[str]:
    return _runtime_memory_requested_scopes(_services_module(), scopes_value, query=query)


def _memory_confidence_score(entry: MemoryEntry, *, now_ts: float | None = None) -> float:
    return _runtime_memory_confidence_score(_services_module(), entry, now_ts=now_ts)


def _memory_confidence_label(score: float) -> str:
    return _runtime_memory_confidence_label(score)


def _memory_source_trail(entry: MemoryEntry) -> str:
    return _runtime_memory_source_trail(entry)


def _json_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _runtime_json_payload_response(payload)


def _expansion_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _runtime_expansion_payload_response(_services_module(), payload)










def _home_plan_from_request(request_text: str) -> dict[str, Any]:
    return _runtime_home_plan_from_request(request_text)


def _slugify_identifier(value: str, *, fallback: str = "item") -> str:
    return _runtime_slugify_identifier(value, fallback=fallback)


def _json_preview(value: Any, *, limit: int = 500) -> str:
    return _runtime_json_preview(value, limit=limit)


def _structured_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return _runtime_structured_diff(previous, current)


def _normalize_automation_config(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    return _runtime_normalize_automation_config(args)


def _automation_entry_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return _runtime_automation_entry_from_draft(draft)


async def _apply_ha_automation_config(automation_id: str, config_payload: dict[str, Any]) -> tuple[bool, str]:
    return await _runtime_apply_ha_automation_config(_services_module(), automation_id, config_payload)


async def _delete_ha_automation_config(automation_id: str) -> tuple[bool, str]:
    return await _runtime_delete_ha_automation_config(_services_module(), automation_id)


def _autonomy_tasks() -> list[dict[str, Any]]:
    return _runtime_autonomy_tasks(_services_module())





def _planner_ready_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return _runtime_planner_ready_nodes(_services_module(), graph)
