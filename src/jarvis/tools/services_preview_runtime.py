"""Plan preview and ambiguity helper runtime helpers for services domains."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any


def tokenized_words(text: str) -> list[str]:
    chars: list[str] = []
    for ch in str(text or "").lower():
        chars.append(ch if (ch.isalnum() or ch in {"_", "'"}) else " ")
    return [token for token in "".join(chars).split() if token]


def is_ambiguous_high_risk_text(services_module: Any, text: str) -> bool:
    s = services_module
    sample = str(text).strip().lower()
    if not sample:
        return False
    words = tokenized_words(sample)
    if not words:
        return False
    has_risk_term = any(term in sample for term in s.HIGH_RISK_INTENT_TERMS)
    if not has_risk_term:
        return False
    has_ambiguous_reference = any(token in s.AMBIGUOUS_REFERENCE_TERMS for token in words)
    has_explicit_target = any(token in s.EXPLICIT_TARGET_TERMS for token in words)
    return has_ambiguous_reference and not has_explicit_target


def is_ambiguous_entity_target(entity_id: str) -> bool:
    clean = str(entity_id or "").strip().lower()
    if "." not in clean:
        return False
    name = clean.split(".", 1)[1]
    words = tokenized_words(name.replace("-", "_"))
    if not words:
        return False
    return any(token in {"all", "group", "everything", "everyone"} for token in words)


def plan_preview_signature(tool_name: str, payload: dict[str, Any]) -> str:
    normalized = {"tool": tool_name, "payload": payload}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def prune_plan_previews(services_module: Any, now_ts: float | None = None) -> None:
    s = services_module
    if not s._pending_plan_previews:
        return
    current = time.time() if now_ts is None else float(now_ts)
    stale = [token for token, item in s._pending_plan_previews.items() if float(item.get("expires_at", 0.0)) <= current]
    for token in stale:
        s._pending_plan_previews.pop(token, None)
    if len(s._pending_plan_previews) <= s.PLAN_PREVIEW_MAX_PENDING:
        return
    overflow = len(s._pending_plan_previews) - s.PLAN_PREVIEW_MAX_PENDING
    oldest = sorted(
        s._pending_plan_previews.items(),
        key=lambda pair: float(pair[1].get("issued_at", 0.0)),
    )[:overflow]
    for token, _ in oldest:
        s._pending_plan_previews.pop(token, None)


def issue_plan_preview_token(services_module: Any, tool_name: str, signature: str, risk: str, summary: str) -> str:
    s = services_module
    now = time.time()
    token = secrets.token_urlsafe(12)
    s._pending_plan_previews[token] = {
        "tool": tool_name,
        "signature": signature,
        "risk": risk,
        "summary": summary,
        "issued_at": now,
        "expires_at": now + s.PLAN_PREVIEW_TTL_SEC,
    }
    prune_plan_previews(s, now)
    return token


def consume_plan_preview_token(services_module: Any, token: str, *, tool_name: str, signature: str) -> bool:
    s = services_module
    if not token:
        return False
    prune_plan_previews(s)
    row = s._pending_plan_previews.get(token)
    if not isinstance(row, dict):
        return False
    if str(row.get("tool", "")) != tool_name:
        return False
    if str(row.get("signature", "")) != signature:
        return False
    s._pending_plan_previews.pop(token, None)
    return True


def plan_preview_message(*, summary: str, risk: str, token: str, ttl_sec: float) -> str:
    ttl = max(1, int(round(ttl_sec)))
    return (
        f"PLAN PREVIEW ({risk} risk): {summary}. "
        f"To execute, resend with preview_token={token} within {ttl}s."
    )


def preview_gate(
    services_module: Any,
    *,
    tool_name: str,
    args: dict[str, Any],
    risk: str,
    summary: str,
    signature_payload: dict[str, Any],
    enforce_default: bool,
) -> str | None:
    s = services_module
    enforce = s._as_bool(args.get("require_preview_ack"), default=enforce_default)
    preview_only = s._as_bool(args.get("preview_only"), default=False) or s._as_bool(args.get("preview"), default=False)
    preview_token = str(args.get("preview_token", "")).strip()
    signature = plan_preview_signature(tool_name, signature_payload)

    if preview_only:
        issued = issue_plan_preview_token(s, tool_name, signature, risk, summary)
        return plan_preview_message(summary=summary, risk=risk, token=issued, ttl_sec=s.PLAN_PREVIEW_TTL_SEC)
    if not enforce:
        return None
    if not preview_token:
        issued = issue_plan_preview_token(s, tool_name, signature, risk, summary)
        return plan_preview_message(summary=summary, risk=risk, token=issued, ttl_sec=s.PLAN_PREVIEW_TTL_SEC)
    if not consume_plan_preview_token(s, preview_token, tool_name=tool_name, signature=signature):
        return "Invalid or expired preview_token. Request a new plan preview with preview_only=true."
    return None
