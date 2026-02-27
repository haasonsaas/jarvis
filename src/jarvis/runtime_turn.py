"""Conversation-turn helper utilities for Jarvis runtime."""

from __future__ import annotations

import math
import re
import time
from contextlib import suppress
from typing import Any, Callable, Mapping

from jarvis.runtime_constants import (
    ACTION_INTENT_TERMS,
    CORRECTION_TERMS,
    FOLLOWUP_CARRYOVER_ACK_TERMS,
    FOLLOWUP_CARRYOVER_MAX_AGE_SEC,
    FOLLOWUP_CARRYOVER_PREFIX_TERMS,
    FOLLOWUP_CARRYOVER_REFERENCE_TERMS,
    FOLLOWUP_CARRYOVER_SHORT_REPLY_MAX_WORDS,
    QUESTION_START_TERMS,
)


def classify_user_intent(text: str) -> str:
    phrase = str(text or "").strip().lower()
    if not phrase:
        return "answer"
    tokens = set(re.findall(r"[a-z']+", phrase))
    has_action = bool(tokens & ACTION_INTENT_TERMS)
    starts_with_question = any(phrase.startswith(f"{term} ") for term in QUESTION_START_TERMS)
    has_question = phrase.endswith("?") or starts_with_question
    if has_action and has_question:
        return "hybrid"
    if has_action:
        return "action"
    return "answer"


def looks_like_user_correction(text: str) -> bool:
    phrase = str(text or "").strip().lower()
    if not phrase:
        return False
    if any(term in phrase for term in CORRECTION_TERMS):
        return True
    return bool(re.search(r"\b(?:no|nope|nah)\b.+\b(?:meant|wanted|said)\b", phrase))


def is_followup_carryover_candidate(
    text: str,
    *,
    context: Mapping[str, Any] | None,
    now_ts: float | None = None,
) -> bool:
    phrase = str(text or "").strip().lower()
    if not phrase:
        return False
    if not isinstance(context, Mapping):
        return False
    previous_text = str(context.get("text", "")).strip()
    previous_intent = str(context.get("intent", "")).strip().lower()
    unresolved = bool(context.get("unresolved", False))
    try:
        previous_ts = float(context.get("timestamp", 0.0))
    except (TypeError, ValueError):
        previous_ts = 0.0
    if not math.isfinite(previous_ts) or previous_ts < 0.0:
        previous_ts = 0.0
    if not previous_text or previous_intent not in {"action", "hybrid"}:
        return False
    if now_ts is None:
        now_value = time.time()
    else:
        try:
            now_value = float(now_ts)
        except (TypeError, ValueError):
            now_value = time.time()
    if not math.isfinite(now_value):
        now_value = time.time()
    if (now_value - previous_ts) > FOLLOWUP_CARRYOVER_MAX_AGE_SEC:
        return False
    if len(phrase) > 220:
        return False
    if any(phrase.startswith(prefix) for prefix in FOLLOWUP_CARRYOVER_PREFIX_TERMS):
        return True
    word_list = [token for token in re.findall(r"[a-z0-9']+", phrase)]
    words = set(word_list)
    if words & FOLLOWUP_CARRYOVER_REFERENCE_TERMS:
        return True
    if not unresolved:
        return False
    if phrase.endswith("?"):
        return False
    if not word_list or len(word_list) > FOLLOWUP_CARRYOVER_SHORT_REPLY_MAX_WORDS:
        return False
    if words.issubset(FOLLOWUP_CARRYOVER_ACK_TERMS):
        return False
    if words & ACTION_INTENT_TERMS:
        return False
    if word_list[0] in QUESTION_START_TERMS:
        return False
    return True


def with_followup_carryover(
    text: str,
    *,
    context: Mapping[str, Any] | None,
    now_ts: float | None = None,
) -> tuple[str, bool]:
    if not is_followup_carryover_candidate(text, context=context, now_ts=now_ts):
        return text, False
    if not isinstance(context, Mapping):
        return text, False
    previous_text = str(context.get("text", "")).strip()[:220]
    unresolved = bool(context.get("unresolved", False))
    policy = (
        "Previous request may still have unresolved slots; preserve target/entity context unless user overrides."
        if unresolved
        else "Preserve prior action context unless the user explicitly overrides target or scope."
    )
    augmented = (
        f"{text}\n\nFollow-up intent carryover:\n"
        f"Previous request: {previous_text}\n"
        f"{policy}"
    )
    return augmented, True


def update_followup_carryover(
    text: str,
    intent_class: str,
    *,
    resolved: bool | None,
    now_ts: float | None = None,
) -> dict[str, Any] | None:
    phrase = str(text or "").strip()
    if not phrase:
        return None
    intent = str(intent_class or "").strip().lower()
    unresolved = intent in {"action", "hybrid"} and resolved is not True
    if now_ts is None:
        timestamp = time.time()
    else:
        try:
            timestamp = float(now_ts)
        except (TypeError, ValueError):
            timestamp = time.time()
    if not math.isfinite(timestamp) or timestamp < 0.0:
        timestamp = time.time()
    return {
        "text": phrase[:280],
        "intent": intent,
        "timestamp": timestamp,
        "unresolved": unresolved,
    }


def turn_tool_summaries_since(
    started_at: float,
    *,
    list_summaries_fn: Callable[..., Any],
) -> list[dict[str, Any]]:
    with suppress(Exception):
        summaries = list_summaries_fn(limit=200)
        if isinstance(summaries, list):
            matched: list[dict[str, Any]] = []
            for item in summaries:
                if not isinstance(item, dict):
                    continue
                timestamp_raw = item.get("timestamp")
                try:
                    timestamp = float(timestamp_raw)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(timestamp) or timestamp < started_at:
                    continue
                name = str(item.get("name", "")).strip().lower()
                if name in {"system_status", "system_status_contract", "tool_summary", "tool_summary_text"}:
                    continue
                matched.append(item)
            return matched
    return []


def completion_success_from_summaries(summaries: list[dict[str, Any]]) -> bool | None:
    if not summaries:
        return None
    success_statuses = {"ok", "dry_run", "noop", "cooldown"}
    failure_statuses = {"error", "denied"}
    has_success = any(str(item.get("status", "")).strip().lower() in success_statuses for item in summaries)
    has_failure = any(str(item.get("status", "")).strip().lower() in failure_statuses for item in summaries)
    if has_success:
        return True
    if has_failure:
        return False
    return None


def tool_call_trace_items(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in summaries:
        if not isinstance(item, dict):
            continue
        try:
            duration = float(item.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        if not math.isfinite(duration) or duration < 0.0:
            duration = 0.0
        calls.append(
            {
                "name": str(item.get("name", "tool")),
                "status": str(item.get("status", "unknown")),
                "duration_ms": duration,
                "detail": str(item.get("detail", "")),
                "effect": str(item.get("effect", "")),
                "risk": str(item.get("risk", "")),
            }
        )
    return calls


def policy_decisions_from_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for item in summaries:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip().lower()
        detail = str(item.get("detail", "")).strip().lower()
        if not status and not detail:
            continue
        if (
            status in {"denied", "dry_run", "cooldown"}
            or detail in {"policy", "circuit_open"}
            or "policy" in detail
            or "preview" in detail
        ):
            decisions.append(
                {
                    "tool": str(item.get("name", "tool")),
                    "status": status,
                    "detail": detail,
                }
            )
    return decisions
