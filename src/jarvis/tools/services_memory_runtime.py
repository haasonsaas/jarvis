"""Memory scope and confidence runtime helpers for services domains."""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any


def normalize_memory_scope(services_module: Any, value: Any) -> str | None:
    s = services_module
    text = str(value or "").strip().lower()
    if text in s.MEMORY_SCOPES:
        return text
    return None


def memory_scope_tag(services_module: Any, scope: str) -> str:
    s = services_module
    return f"{s.MEMORY_SCOPE_TAG_PREFIX}{scope}"


def memory_scope_from_tags(services_module: Any, tags: list[str] | None) -> str | None:
    s = services_module
    for tag in tags or []:
        text = str(tag).strip().lower()
        if text.startswith(s.MEMORY_SCOPE_TAG_PREFIX):
            scope = text[len(s.MEMORY_SCOPE_TAG_PREFIX) :]
            if scope in s.MEMORY_SCOPES:
                return scope
    return None


def infer_memory_scope(*, kind: str, source: str) -> str:
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


def memory_scope_for_add(
    services_module: Any,
    *,
    kind: str,
    source: str,
    tags: list[str],
    requested_scope: Any,
) -> str:
    explicit = normalize_memory_scope(services_module, requested_scope)
    if explicit:
        return explicit
    tagged = memory_scope_from_tags(services_module, tags)
    if tagged:
        return tagged
    return infer_memory_scope(kind=kind, source=source)


def memory_scope_tags(services_module: Any, tags: list[str], scope: str) -> list[str]:
    s = services_module
    cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
    filtered = [tag for tag in cleaned if not tag.lower().startswith(s.MEMORY_SCOPE_TAG_PREFIX)]
    filtered.append(memory_scope_tag(s, scope))
    return filtered


def memory_visible_tags(services_module: Any, tags: list[str]) -> list[str]:
    s = services_module
    return [tag for tag in tags if not str(tag).strip().lower().startswith(s.MEMORY_SCOPE_TAG_PREFIX)]


def memory_entry_scope(services_module: Any, entry: Any) -> str:
    tagged = memory_scope_from_tags(services_module, entry.tags)
    if tagged:
        return tagged
    return infer_memory_scope(kind=str(entry.kind), source=str(entry.source))


def memory_policy_scopes_for_query(services_module: Any, query: str) -> list[str]:
    s = services_module
    tokens = {token for token in re.findall(r"[a-z0-9_']+", str(query or "").lower()) if token}
    if not tokens:
        return sorted(s.MEMORY_SCOPES)
    for scope, hints in s.MEMORY_QUERY_SCOPE_HINTS.items():
        if tokens & hints:
            return sorted({scope, "preferences"})
    return sorted(s.MEMORY_SCOPES)


def memory_requested_scopes(services_module: Any, scopes_value: Any, *, query: str = "") -> list[str]:
    if isinstance(scopes_value, list):
        cleaned = []
        for item in scopes_value:
            scope = normalize_memory_scope(services_module, item)
            if scope and scope not in cleaned:
                cleaned.append(scope)
        if cleaned:
            return cleaned
    fallback_single = normalize_memory_scope(services_module, scopes_value)
    if fallback_single:
        return [fallback_single]
    return memory_policy_scopes_for_query(services_module, query)


def memory_confidence_score(services_module: Any, entry: Any, *, now_ts: float | None = None) -> float:
    s = services_module
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
    sensitivity = s._as_float(getattr(entry, "sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    confidence = (0.55 * retrieval_score) + (0.30 * recency) + (0.15 * source_confidence)
    confidence *= max(0.4, 1.0 - (0.35 * sensitivity))
    return s._as_float(confidence, 0.0, minimum=0.0, maximum=1.0)


def memory_confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def memory_source_trail(entry: Any) -> str:
    source = str(getattr(entry, "source", "")).strip() or "unknown"
    created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(entry.created_at)))
    return f"id={entry.id};source={source};created_at={created}"


def json_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def expansion_payload_response(services_module: Any, payload: dict[str, Any]) -> dict[str, Any]:
    services_module._persist_expansion_state()
    return json_payload_response(payload)
