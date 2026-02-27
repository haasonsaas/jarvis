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
import re  # noqa: F401  # accessed by domain modules via services module alias
import smtplib  # noqa: F401  # accessed by domain modules via services module alias
import sys
import time
from contextlib import suppress  # noqa: F401  # accessed by domain modules via services module alias
from pathlib import Path
from typing import Any
from urllib.parse import urlparse  # noqa: F401  # accessed by domain modules via services module alias

import aiohttp  # noqa: F401

from jarvis.config import Config
from jarvis.skills import SkillRegistry
from jarvis.tool_policy import is_tool_allowed
from jarvis.tool_summary import record_summary, list_summaries  # noqa: F401  # accessed via services module alias
from jarvis.memory import MemoryStore
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
from jarvis.tools import services_defaults as _services_defaults
from jarvis.tools.services_server import create_services_server  # noqa: F401  # compatibility export for callers
from jarvis.tools.services_state_facade_runtime import (
    append_quality_report as _facade_append_quality_report,
    bind_runtime_state as _facade_bind_runtime_state,
    expansion_state_payload as _facade_expansion_state_payload,
    json_safe_clone as _facade_json_safe_clone,
    load_expansion_state as _facade_load_expansion_state,
    persist_expansion_state as _facade_persist_expansion_state,
    quality_reports_snapshot as _facade_quality_reports_snapshot,
    replace_state_dict as _facade_replace_state_dict,
)
from jarvis.tools.services_integrations_facade_runtime import (
    capture_note as _facade_capture_note,
    capture_note_notion as _facade_capture_note_notion,
    evaluate_release_channel as _facade_evaluate_release_channel,
    load_release_channel_config as _facade_load_release_channel_config,
    notion_configured as _facade_notion_configured,
    run_release_channel_check as _facade_run_release_channel_check,
    write_quality_report_artifact as _facade_write_quality_report_artifact,
)
from jarvis.tools.services_identity_facade_runtime import (
    identity_audit_fields as _facade_identity_audit_fields,
    identity_authorize as _facade_identity_authorize,
    identity_context as _facade_identity_context,
    identity_enriched_audit as _facade_identity_enriched_audit,
    identity_trust_domain as _facade_identity_trust_domain,
)
from jarvis.tools.services_status_facade_runtime import (
    duration_p95_ms as _facade_duration_p95_ms,
    expansion_snapshot as _facade_expansion_snapshot,
    health_rollup as _facade_health_rollup,
    identity_status_snapshot as _facade_identity_status_snapshot,
    integration_health_snapshot as _facade_integration_health_snapshot,
    jarvis_scorecard_snapshot as _facade_jarvis_scorecard_snapshot,
    observability_snapshot as _facade_observability_snapshot,
    recent_tool_rows as _facade_recent_tool_rows,
    score_label as _facade_score_label,
    skills_status_snapshot as _facade_skills_status_snapshot,
    voice_attention_snapshot as _facade_voice_attention_snapshot,
)
from jarvis.tools.services_ha_facade_runtime import (
    ha_call_service as _facade_ha_call_service,
    ha_conversation_speech as _facade_ha_conversation_speech,
    ha_get_domain_services as _facade_ha_get_domain_services,
    ha_get_json as _facade_ha_get_json,
    ha_get_state as _facade_ha_get_state,
    ha_render_template as _facade_ha_render_template,
    ha_request_json as _facade_ha_request_json,
)
from jarvis.tools.services_comms_facade_runtime import (
    collect_json_lists_by_key as _facade_collect_json_lists_by_key,
    parse_calendar_event_timestamp as _facade_parse_calendar_event_timestamp,
    record_email_history as _facade_record_email_history,
    record_inbound_webhook_event as _facade_record_inbound_webhook_event,
    send_email_sync as _facade_send_email_sync,
    webhook_host_allowed as _facade_webhook_host_allowed,
)
from jarvis.tools.services_recovery_runtime import (
    RecoveryOperation as _runtime_RecoveryOperation,
)
from jarvis.tools.services_recovery_facade_runtime import (
    append_dead_letter_entry as _facade_append_dead_letter_entry,
    dead_letter_enqueue as _facade_dead_letter_enqueue,
    dead_letter_matches as _facade_dead_letter_matches,
    dead_letter_queue_status as _facade_dead_letter_queue_status,
    read_dead_letter_entries as _facade_read_dead_letter_entries,
    read_recovery_journal_entries as _facade_read_recovery_journal_entries,
    recovery_begin as _facade_recovery_begin,
    recovery_finish as _facade_recovery_finish,
    recovery_journal_status as _facade_recovery_journal_status,
    recovery_reconcile_interrupted as _facade_recovery_reconcile_interrupted,
    tool_response_success as _facade_tool_response_success,
    tool_response_text as _facade_tool_response_text,
    write_dead_letter_entries as _facade_write_dead_letter_entries,
    write_recovery_journal_entry as _facade_write_recovery_journal_entry,
)
from jarvis.tools.services_audit_facade_runtime import (
    apply_retention_policies as _facade_apply_retention_policies,
    audit as _facade_audit,
    audit_decision_explanation as _facade_audit_decision_explanation,
    audit_outcome as _facade_audit_outcome,
    audit_reason_code as _facade_audit_reason_code,
    audit_status as _facade_audit_status,
    configure_audit_encryption as _facade_configure_audit_encryption,
    contains_pii as _facade_contains_pii,
    decode_audit_line as _facade_decode_audit_line,
    encrypt_audit_line as _facade_encrypt_audit_line,
    humanize_chain_token as _facade_humanize_chain_token,
    metadata_only_audit_details as _facade_metadata_only_audit_details,
    prune_audit_file as _facade_prune_audit_file,
    redact_sensitive_for_audit as _facade_redact_sensitive_for_audit,
    rotate_audit_log_if_needed as _facade_rotate_audit_log_if_needed,
    sanitize_inbound_headers as _facade_sanitize_inbound_headers,
    sanitize_inbound_payload as _facade_sanitize_inbound_payload,
)
from jarvis.tools.services_schedule_facade_runtime import (
    allocate_reminder_id as _facade_allocate_reminder_id,
    allocate_timer_id as _facade_allocate_timer_id,
    duration_seconds as _facade_duration_seconds,
    format_duration as _facade_format_duration,
    load_reminders_from_store as _facade_load_reminders_from_store,
    load_timers_from_store as _facade_load_timers_from_store,
    local_timezone as _facade_local_timezone,
    parse_datetime_text as _facade_parse_datetime_text,
    parse_due_timestamp as _facade_parse_due_timestamp,
    prune_timers as _facade_prune_timers,
    reminder_status as _facade_reminder_status,
    timer_status as _facade_timer_status,
    timestamp_to_iso_utc as _facade_timestamp_to_iso_utc,
)
from jarvis.tools.services_memory_facade_runtime import (
    expansion_payload_response as _facade_expansion_payload_response,
    infer_memory_scope as _facade_infer_memory_scope,
    json_payload_response as _facade_json_payload_response,
    memory_confidence_label as _facade_memory_confidence_label,
    memory_confidence_score as _facade_memory_confidence_score,
    memory_entry_scope as _facade_memory_entry_scope,
    memory_policy_scopes_for_query as _facade_memory_policy_scopes_for_query,
    memory_requested_scopes as _facade_memory_requested_scopes,
    memory_scope_for_add as _facade_memory_scope_for_add,
    memory_scope_from_tags as _facade_memory_scope_from_tags,
    memory_scope_tag as _facade_memory_scope_tag,
    memory_scope_tags as _facade_memory_scope_tags,
    memory_source_trail as _facade_memory_source_trail,
    memory_visible_tags as _facade_memory_visible_tags,
    normalize_memory_scope as _facade_normalize_memory_scope,
)
from jarvis.tools.services_preview_facade_runtime import (
    consume_plan_preview_token as _facade_consume_plan_preview_token,
    is_ambiguous_entity_target as _facade_is_ambiguous_entity_target,
    is_ambiguous_high_risk_text as _facade_is_ambiguous_high_risk_text,
    issue_plan_preview_token as _facade_issue_plan_preview_token,
    plan_preview_message as _facade_plan_preview_message,
    plan_preview_signature as _facade_plan_preview_signature,
    preview_gate as _facade_preview_gate,
    prune_plan_previews as _facade_prune_plan_previews,
    tokenized_words as _facade_tokenized_words,
)
from jarvis.tools.services_circuit_facade_runtime import (
    ensure_circuit_breaker_state as _facade_ensure_circuit_breaker_state,
    integration_circuit_open as _facade_integration_circuit_open,
    integration_circuit_open_message as _facade_integration_circuit_open_message,
    integration_circuit_snapshot as _facade_integration_circuit_snapshot,
    integration_for_tool as _facade_integration_for_tool,
    integration_record_failure as _facade_integration_record_failure,
    integration_record_success as _facade_integration_record_success,
)
from jarvis.tools.services_policy_facade_runtime import (
    hhmm_to_minutes as _facade_hhmm_to_minutes,
    identity_profile_level as _facade_identity_profile_level,
    normalize_nudge_policy as _facade_normalize_nudge_policy,
    profile_rank as _facade_profile_rank,
    prune_guest_sessions as _facade_prune_guest_sessions,
    quiet_window_active as _facade_quiet_window_active,
    register_guest_session as _facade_register_guest_session,
    resolve_guest_session as _facade_resolve_guest_session,
)
from jarvis.tools.services_planner_facade_runtime import (
    apply_ha_automation_config as _facade_apply_ha_automation_config,
    automation_entry_from_draft as _facade_automation_entry_from_draft,
    autonomy_tasks as _facade_autonomy_tasks,
    delete_ha_automation_config as _facade_delete_ha_automation_config,
    home_plan_from_request as _facade_home_plan_from_request,
    json_preview as _facade_json_preview,
    normalize_automation_config as _facade_normalize_automation_config,
    planner_ready_nodes as _facade_planner_ready_nodes,
    slugify_identifier as _facade_slugify_identifier,
    structured_diff as _facade_structured_diff,
)
from jarvis.tools.services_action_facade_runtime import (
    action_key as _facade_action_key,
    cooldown_active as _facade_cooldown_active,
    prune_action_history as _facade_prune_action_history,
    retry_backoff_delay as _facade_retry_backoff_delay,
    touch_action as _facade_touch_action,
)
from jarvis.tools.services_coercion_facade_runtime import (
    as_bool as _facade_as_bool,
    as_exact_int as _facade_as_exact_int,
    as_float as _facade_as_float,
    as_int as _facade_as_int,
    as_str_list as _facade_as_str_list,
    effective_act_timeout as _facade_effective_act_timeout,
)
from jarvis.tools.services_home_policy_runtime import (
    extract_area_from_entity as _runtime_extract_area_from_entity,
    home_action_is_loud as _runtime_home_action_is_loud,
    home_area_policy_violation as _runtime_home_area_policy_violation,
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
)
from jarvis.tools.services_domains.trust_memory import (  # noqa: F401  # compatibility exports for tests/importers
    memory_add,
    memory_update,
    memory_forget,
    memory_search,
    memory_status,
    memory_recent,
    memory_summary_add,
    memory_summary_list,
    memory_governance,
)
from jarvis.tools.services_domains.trust_identity import (  # noqa: F401  # compatibility exports for tests/importers
    identity_trust,
)

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency fallback
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Re-export static defaults for compatibility with runtime/domain helpers that
# access them through the `jarvis.tools.services` module alias.
AUDIT_LOG = _services_defaults.AUDIT_LOG
DEFAULT_RECOVERY_JOURNAL = _services_defaults.DEFAULT_RECOVERY_JOURNAL
DEFAULT_DEAD_LETTER_QUEUE = _services_defaults.DEFAULT_DEAD_LETTER_QUEUE
DEFAULT_EXPANSION_STATE = _services_defaults.DEFAULT_EXPANSION_STATE
DEFAULT_RELEASE_CHANNEL_CONFIG = _services_defaults.DEFAULT_RELEASE_CHANNEL_CONFIG
QUALITY_REPORT_DIR_DEFAULT = _services_defaults.QUALITY_REPORT_DIR_DEFAULT
NOTES_CAPTURE_DIR_DEFAULT = _services_defaults.NOTES_CAPTURE_DIR_DEFAULT

ACTION_COOLDOWN_SEC = _services_defaults.ACTION_COOLDOWN_SEC
ACTION_HISTORY_RETENTION_SEC = _services_defaults.ACTION_HISTORY_RETENTION_SEC
ACTION_HISTORY_MAX_ENTRIES = _services_defaults.ACTION_HISTORY_MAX_ENTRIES
HA_STATE_CACHE_TTL_SEC = _services_defaults.HA_STATE_CACHE_TTL_SEC
TODOIST_LIST_MAX_RETRIES = _services_defaults.TODOIST_LIST_MAX_RETRIES
RETRY_BASE_DELAY_SEC = _services_defaults.RETRY_BASE_DELAY_SEC
RETRY_MAX_DELAY_SEC = _services_defaults.RETRY_MAX_DELAY_SEC
RETRY_JITTER_RATIO = _services_defaults.RETRY_JITTER_RATIO
SYSTEM_STATUS_CONTRACT_VERSION = _services_defaults.SYSTEM_STATUS_CONTRACT_VERSION
HA_CONVERSATION_MAX_TEXT_CHARS = _services_defaults.HA_CONVERSATION_MAX_TEXT_CHARS
TIMER_MAX_SECONDS = _services_defaults.TIMER_MAX_SECONDS
TIMER_MAX_ACTIVE = _services_defaults.TIMER_MAX_ACTIVE
REMINDER_MAX_ACTIVE = _services_defaults.REMINDER_MAX_ACTIVE
CALENDAR_DEFAULT_WINDOW_HOURS = _services_defaults.CALENDAR_DEFAULT_WINDOW_HOURS
CALENDAR_MAX_WINDOW_HOURS = _services_defaults.CALENDAR_MAX_WINDOW_HOURS
PLAN_PREVIEW_TTL_SEC = _services_defaults.PLAN_PREVIEW_TTL_SEC
PLAN_PREVIEW_MAX_PENDING = _services_defaults.PLAN_PREVIEW_MAX_PENDING
CACHED_QUALITY_REPORT_MAX = _services_defaults.CACHED_QUALITY_REPORT_MAX
GUEST_SESSION_DEFAULT_TTL_SEC = _services_defaults.GUEST_SESSION_DEFAULT_TTL_SEC
GUEST_SESSION_MAX_TTL_SEC = _services_defaults.GUEST_SESSION_MAX_TTL_SEC
HOME_TASK_MAX_TRACKED = _services_defaults.HOME_TASK_MAX_TRACKED
PLANNER_TASK_GRAPH_MAX = _services_defaults.PLANNER_TASK_GRAPH_MAX
DEFERRED_ACTION_MAX = _services_defaults.DEFERRED_ACTION_MAX
NUDGE_RECENT_DISPATCH_MAX = _services_defaults.NUDGE_RECENT_DISPATCH_MAX
HOME_AUTOMATION_MAX_TRACKED = _services_defaults.HOME_AUTOMATION_MAX_TRACKED
AUTONOMY_CYCLE_HISTORY_MAX = _services_defaults.AUTONOMY_CYCLE_HISTORY_MAX
RELEASE_CHANNELS = _services_defaults.RELEASE_CHANNELS
NOTION_API_VERSION = _services_defaults.NOTION_API_VERSION
SKILL_SANDBOX_TEMPLATES = _services_defaults.SKILL_SANDBOX_TEMPLATES
CIRCUIT_BREAKER_FAILURE_THRESHOLD = _services_defaults.CIRCUIT_BREAKER_FAILURE_THRESHOLD
CIRCUIT_BREAKER_BASE_COOLDOWN_SEC = _services_defaults.CIRCUIT_BREAKER_BASE_COOLDOWN_SEC
CIRCUIT_BREAKER_MAX_COOLDOWN_SEC = _services_defaults.CIRCUIT_BREAKER_MAX_COOLDOWN_SEC
CIRCUIT_BREAKER_ERROR_CODES = _services_defaults.CIRCUIT_BREAKER_ERROR_CODES
_DURATION_SEGMENT_RE = _services_defaults._DURATION_SEGMENT_RE
_PII_PATTERNS = _services_defaults._PII_PATTERNS

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
_proactive_state: dict[str, Any] = _services_defaults.default_proactive_state()
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
_privacy_posture: dict[str, Any] = _services_defaults.default_privacy_posture()
_motion_safety_envelope: dict[str, Any] = _services_defaults.default_motion_safety_envelope()
_release_channel_state: dict[str, Any] = _services_defaults.default_release_channel_state()
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
    _facade_bind_runtime_state(config, memory_store)


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


_configure_audit_encryption = _facade_configure_audit_encryption
_encrypt_audit_line = _facade_encrypt_audit_line
_decode_audit_line = _facade_decode_audit_line


def decode_audit_entry_line(line: str) -> dict[str, Any] | None:
    return _decode_audit_line(line)


_audit_outcome = _facade_audit_outcome
_audit_reason_code = _facade_audit_reason_code
_humanize_chain_token = _facade_humanize_chain_token
_audit_decision_explanation = _facade_audit_decision_explanation
_audit = _facade_audit
_rotate_audit_log_if_needed = _facade_rotate_audit_log_if_needed
_redact_sensitive_for_audit = _facade_redact_sensitive_for_audit
_metadata_only_audit_details = _facade_metadata_only_audit_details
_sanitize_inbound_headers = _facade_sanitize_inbound_headers
_sanitize_inbound_payload = _facade_sanitize_inbound_payload
_contains_pii = _facade_contains_pii


_identity_context = _facade_identity_context
_identity_audit_fields = _facade_identity_audit_fields
_identity_trust_domain = _facade_identity_trust_domain
_identity_authorize = _facade_identity_authorize
_identity_enriched_audit = _facade_identity_enriched_audit


_tokenized_words = _facade_tokenized_words
_is_ambiguous_high_risk_text = _facade_is_ambiguous_high_risk_text
_is_ambiguous_entity_target = _facade_is_ambiguous_entity_target
_plan_preview_signature = _facade_plan_preview_signature
_prune_plan_previews = _facade_prune_plan_previews
_issue_plan_preview_token = _facade_issue_plan_preview_token
_consume_plan_preview_token = _facade_consume_plan_preview_token


def _plan_preview_message(*, summary: str, risk: str, token: str, ttl_sec: float = PLAN_PREVIEW_TTL_SEC) -> str:
    return _facade_plan_preview_message(summary=summary, risk=risk, token=token, ttl_sec=ttl_sec)


_preview_gate = _facade_preview_gate


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


_as_bool = _facade_as_bool
_as_int = _facade_as_int
_as_exact_int = _facade_as_exact_int
_as_float = _facade_as_float
_effective_act_timeout = _facade_effective_act_timeout


_integration_for_tool = _facade_integration_for_tool
_ensure_circuit_breaker_state = _facade_ensure_circuit_breaker_state
_integration_circuit_open = _facade_integration_circuit_open
_integration_record_failure = _facade_integration_record_failure
_integration_record_success = _facade_integration_record_success
_integration_circuit_snapshot = _facade_integration_circuit_snapshot
_integration_circuit_open_message = _facade_integration_circuit_open_message


_normalize_nudge_policy = _facade_normalize_nudge_policy
_hhmm_to_minutes = _facade_hhmm_to_minutes
_quiet_window_active = _facade_quiet_window_active
_identity_profile_level = _facade_identity_profile_level
_profile_rank = _facade_profile_rank
_prune_guest_sessions = _facade_prune_guest_sessions
_resolve_guest_session = _facade_resolve_guest_session
_register_guest_session = _facade_register_guest_session


def _extract_area_from_entity(entity_id: str) -> str:
    return _runtime_extract_area_from_entity(entity_id)


def _home_action_is_loud(*, domain: str, action: str, data: dict[str, Any] | None = None) -> bool:
    return _runtime_home_action_is_loud(domain=domain, action=action, data=data)


def _home_area_policy_violation(
    *,
    domain: str,
    action: str,
    entity_id: str,
    data: dict[str, Any] | None = None,
    now_ts: float | None = None,
) -> tuple[bool, str]:
    return _runtime_home_area_policy_violation(
        _services_module(),
        domain=domain,
        action=action,
        entity_id=entity_id,
        data=data,
        now_ts=now_ts,
    )


def _quality_reports_snapshot(*, limit: int = 10) -> list[dict[str, Any]]:
    return _facade_quality_reports_snapshot(limit=limit)


def _append_quality_report(report: dict[str, Any]) -> None:
    _facade_append_quality_report(report)


def _json_safe_clone(value: Any) -> Any:
    return _facade_json_safe_clone(value)


def _replace_state_dict(target: dict[str, Any], source: Any) -> None:
    _facade_replace_state_dict(target, source)


def _expansion_state_payload() -> dict[str, Any]:
    return _facade_expansion_state_payload()


def _persist_expansion_state() -> None:
    _facade_persist_expansion_state()


def _load_expansion_state() -> None:
    _facade_load_expansion_state()


_run_release_channel_check = _facade_run_release_channel_check
_load_release_channel_config = _facade_load_release_channel_config
_evaluate_release_channel = _facade_evaluate_release_channel
_write_quality_report_artifact = _facade_write_quality_report_artifact
_capture_note = _facade_capture_note
_notion_configured = _facade_notion_configured
_capture_note_notion = _facade_capture_note_notion


_duration_seconds = _facade_duration_seconds
_local_timezone = _facade_local_timezone
_parse_datetime_text = _facade_parse_datetime_text
_parse_due_timestamp = _facade_parse_due_timestamp
_timestamp_to_iso_utc = _facade_timestamp_to_iso_utc
_format_duration = _facade_format_duration
_allocate_timer_id = _facade_allocate_timer_id
_allocate_reminder_id = _facade_allocate_reminder_id


def _retry_backoff_delay(
    attempt_index: int,
    *,
    base_delay_sec: float = RETRY_BASE_DELAY_SEC,
    max_delay_sec: float = RETRY_MAX_DELAY_SEC,
    jitter_ratio: float = RETRY_JITTER_RATIO,
    jitter_sample: float | None = None,
) -> float:
    return _facade_retry_backoff_delay(
        attempt_index,
        base_delay_sec=base_delay_sec,
        max_delay_sec=max_delay_sec,
        jitter_ratio=jitter_ratio,
        jitter_sample=jitter_sample,
    )


_as_str_list = _facade_as_str_list


_action_key = _facade_action_key
_prune_action_history = _facade_prune_action_history
_cooldown_active = _facade_cooldown_active
_touch_action = _facade_touch_action


_audit_status = _facade_audit_status

_read_recovery_journal_entries = _facade_read_recovery_journal_entries
_write_recovery_journal_entry = _facade_write_recovery_journal_entry
_recovery_begin = _facade_recovery_begin
_recovery_finish = _facade_recovery_finish


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


_recovery_reconcile_interrupted = _facade_recovery_reconcile_interrupted
_recovery_journal_status = _facade_recovery_journal_status
_read_dead_letter_entries = _facade_read_dead_letter_entries
_write_dead_letter_entries = _facade_write_dead_letter_entries
_append_dead_letter_entry = _facade_append_dead_letter_entry
_dead_letter_matches = _facade_dead_letter_matches
_dead_letter_queue_status = _facade_dead_letter_queue_status
_dead_letter_enqueue = _facade_dead_letter_enqueue
_tool_response_text = _facade_tool_response_text
_tool_response_success = _facade_tool_response_success


_prune_audit_file = _facade_prune_audit_file
_apply_retention_policies = _facade_apply_retention_policies


def _prune_timers(now_mono: float | None = None) -> None:
    _facade_prune_timers(now_mono=now_mono)


_timer_status = _facade_timer_status


_load_timers_from_store = _facade_load_timers_from_store


_reminder_status = _facade_reminder_status


_load_reminders_from_store = _facade_load_reminders_from_store


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


_ha_get_state = _facade_ha_get_state
_ha_get_domain_services = _facade_ha_get_domain_services
_ha_call_service = _facade_ha_call_service
_ha_get_json = _facade_ha_get_json
_ha_request_json = _facade_ha_request_json
_ha_render_template = _facade_ha_render_template


_collect_json_lists_by_key = _facade_collect_json_lists_by_key
_parse_calendar_event_timestamp = _facade_parse_calendar_event_timestamp
_webhook_host_allowed = _facade_webhook_host_allowed
record_inbound_webhook_event = _facade_record_inbound_webhook_event


_integration_health_snapshot = _facade_integration_health_snapshot
_identity_status_snapshot = _facade_identity_status_snapshot
_voice_attention_snapshot = _facade_voice_attention_snapshot
_observability_snapshot = _facade_observability_snapshot
_skills_status_snapshot = _facade_skills_status_snapshot
_expansion_snapshot = _facade_expansion_snapshot


_health_rollup = _facade_health_rollup
_score_label = _facade_score_label
_recent_tool_rows = _facade_recent_tool_rows
_duration_p95_ms = _facade_duration_p95_ms


_jarvis_scorecard_snapshot = _facade_jarvis_scorecard_snapshot


# ── Home Assistant ────────────────────────────────────────────

_ha_conversation_speech = _facade_ha_conversation_speech


_record_email_history = _facade_record_email_history
_send_email_sync = _facade_send_email_sync






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

_normalize_memory_scope = _facade_normalize_memory_scope
_memory_scope_tag = _facade_memory_scope_tag
_memory_scope_from_tags = _facade_memory_scope_from_tags
_infer_memory_scope = _facade_infer_memory_scope
_memory_scope_for_add = _facade_memory_scope_for_add
_memory_scope_tags = _facade_memory_scope_tags
_memory_visible_tags = _facade_memory_visible_tags
_memory_entry_scope = _facade_memory_entry_scope
_memory_policy_scopes_for_query = _facade_memory_policy_scopes_for_query
_memory_requested_scopes = _facade_memory_requested_scopes
_memory_confidence_score = _facade_memory_confidence_score
_memory_confidence_label = _facade_memory_confidence_label
_memory_source_trail = _facade_memory_source_trail
_json_payload_response = _facade_json_payload_response
_expansion_payload_response = _facade_expansion_payload_response










_home_plan_from_request = _facade_home_plan_from_request
_slugify_identifier = _facade_slugify_identifier
_json_preview = _facade_json_preview
_structured_diff = _facade_structured_diff
_normalize_automation_config = _facade_normalize_automation_config
_automation_entry_from_draft = _facade_automation_entry_from_draft
_apply_ha_automation_config = _facade_apply_ha_automation_config
_delete_ha_automation_config = _facade_delete_ha_automation_config
_autonomy_tasks = _facade_autonomy_tasks
_planner_ready_nodes = _facade_planner_ready_nodes
