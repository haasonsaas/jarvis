"""Shared services defaults and static constants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Audit log in user's home dir for predictable location.
AUDIT_LOG = Path.home() / ".jarvis" / "audit.jsonl"
DEFAULT_RECOVERY_JOURNAL = Path.home() / ".jarvis" / "recovery-journal.jsonl"
DEFAULT_DEAD_LETTER_QUEUE = Path.home() / ".jarvis" / "dead-letter-queue.jsonl"
DEFAULT_EXPANSION_STATE = Path.home() / ".jarvis" / "expansion-state.json"
DEFAULT_RELEASE_CHANNEL_CONFIG = Path("config/release-channels.json")
DEFAULT_POLICY_ENGINE_CONFIG = Path("config/policy-engine-v1.json")
QUALITY_REPORT_DIR_DEFAULT = Path.home() / ".jarvis" / "quality-reports"
NOTES_CAPTURE_DIR_DEFAULT = Path.home() / ".jarvis" / "notes"

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
NUDGE_RECENT_DISPATCH_MAX = 500
HOME_AUTOMATION_MAX_TRACKED = 300
AUTONOMY_CYCLE_HISTORY_MAX = 200
AUTONOMY_REPLAN_DRAFT_MAX = 400
GOAL_STACK_MAX = 100
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
_DURATION_UNITS_SECONDS: dict[str, float] = {
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "second": 1.0,
    "seconds": 1.0,
}


def _contains_ssn_like(text: str) -> bool:
    sample = str(text or "")
    for index in range(0, max(0, len(sample) - 10)):
        chunk = sample[index : index + 11]
        if (
            chunk[3] == "-"
            and chunk[6] == "-"
            and chunk[:3].isdigit()
            and chunk[4:6].isdigit()
            and chunk[7:].isdigit()
        ):
            return True
    return False


def _contains_card_like(text: str) -> bool:
    sample = str(text or "")
    run_chars: list[str] = []
    for ch in sample + " ":
        if ch.isdigit() or ch in {" ", "-"}:
            run_chars.append(ch)
            continue
        if run_chars:
            digits = [item for item in run_chars if item.isdigit()]
            if 13 <= len(digits) <= 16:
                return True
            run_chars.clear()
    return False


def _contains_phone_like(text: str) -> bool:
    sample = str(text or "")
    current_digits = 0
    for ch in sample + " ":
        if ch.isdigit():
            current_digits += 1
            continue
        if ch in {" ", "-", ".", "(", ")", "+"}:
            continue
        if current_digits in {10, 11}:
            return True
        current_digits = 0
    return current_digits in {10, 11}


def _contains_email_like(text: str) -> bool:
    for token in str(text or "").replace(",", " ").replace(";", " ").split():
        candidate = token.strip().lower()
        if "@" not in candidate or "." not in candidate:
            continue
        if candidate.count("@") != 1:
            continue
        local, domain = candidate.split("@", 1)
        if not local or not domain or "." not in domain:
            continue
        if len(local) > 128 or len(domain) > 255:
            continue
        valid_local = all(ch.isalnum() or ch in {".", "_", "%", "+", "-"} for ch in local)
        valid_domain = all(ch.isalnum() or ch in {".", "-"} for ch in domain)
        if not (valid_local and valid_domain):
            continue
        top_level = domain.rsplit(".", 1)[-1]
        if len(top_level) >= 2 and top_level.isalpha():
            return True
    return False


_PII_PATTERNS = (
    _contains_ssn_like,
    _contains_card_like,
    _contains_phone_like,
    _contains_email_like,
)


def default_proactive_state() -> dict[str, Any]:
    return {
        "pending_follow_through": [],
        "follow_through_seq": 1,
        "follow_through_enqueued_total": 0,
        "follow_through_executed_total": 0,
        "follow_through_deduped_total": 0,
        "follow_through_pruned_total": 0,
        "last_follow_through_at": 0.0,
        "digest_snoozed_until": 0.0,
        "last_briefing_at": 0.0,
        "briefings_total": 0,
        "last_briefing_mode": "",
        "last_digest_at": 0.0,
        "digests_total": 0,
        "digest_items_total": 0,
        "digest_deduped_total": 0,
        "nudge_decisions_total": 0,
        "nudge_interrupt_total": 0,
        "nudge_notify_total": 0,
        "nudge_defer_total": 0,
        "nudge_deduped_total": 0,
        "last_nudge_decision_at": 0.0,
        "last_nudge_dedupe_at": 0.0,
        "nudge_recent_dispatches": [],
        "approval_requests": [],
        "approval_seq": 1,
        "approval_requests_total": 0,
        "approval_approved_total": 0,
        "approval_rejected_total": 0,
        "approval_consumed_total": 0,
        "approval_expired_total": 0,
        "approval_pruned_total": 0,
        "effect_verification_total": 0,
        "effect_verification_passed_total": 0,
        "effect_verification_failed_total": 0,
        "autonomy_replan_seq": 1,
        "identity_trust_scores": {},
    }


def default_privacy_posture() -> dict[str, Any]:
    return {
        "state": "normal",
        "reason": "startup",
        "updated_at": 0.0,
    }


def default_motion_safety_envelope() -> dict[str, Any]:
    return {
        "proximity_limit_cm": 35.0,
        "max_yaw_deg": 45.0,
        "max_pitch_deg": 20.0,
        "max_roll_deg": 15.0,
        "hardware_state": "normal",
        "updated_at": 0.0,
    }


def default_release_channel_state() -> dict[str, Any]:
    return {
        "active_channel": "dev",
        "last_check_at": 0.0,
        "last_check_channel": "",
        "last_check_passed": False,
        "migration_checks": [],
    }
