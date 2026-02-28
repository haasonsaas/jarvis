"""Policy/session runtime helpers for services domains."""

from __future__ import annotations

import secrets
import time
from typing import Any


def normalize_nudge_policy(value: Any) -> str:
    normalized = str(value or "adaptive").strip().lower()
    if normalized in {"interrupt", "defer", "adaptive"}:
        return normalized
    return "adaptive"


def hhmm_to_minutes(value: str) -> int | None:
    text = str(value or "").strip()
    if ":" not in text:
        return None
    parts = text.split(":")
    if len(parts) != 2:
        return None
    hours_text = parts[0].strip()
    minutes_text = parts[1].strip()
    if not (hours_text.isdigit() and minutes_text.isdigit() and len(minutes_text) == 2):
        return None
    hours = int(hours_text)
    minutes = int(minutes_text)
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    return (hours * 60) + minutes


def quiet_window_active(services_module: Any, *, now_ts: float | None = None) -> bool:
    s = services_module
    start = hhmm_to_minutes(s._nudge_quiet_hours_start)
    end = hhmm_to_minutes(s._nudge_quiet_hours_end)
    if start is None or end is None or start == end:
        return False
    local = time.localtime(time.time() if now_ts is None else float(now_ts))
    minute = (local.tm_hour * 60) + local.tm_min
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def identity_profile_level(profile: str) -> str:
    normalized = str(profile or "control").strip().lower()
    if normalized in {"deny", "guest", "readonly", "control", "trusted"}:
        return normalized
    return "control"


def profile_rank(profile: str) -> int:
    order = {
        "deny": 0,
        "guest": 1,
        "readonly": 2,
        "control": 3,
        "trusted": 4,
    }
    return order.get(identity_profile_level(profile), 3)


def prune_guest_sessions(services_module: Any, *, now_ts: float | None = None) -> None:
    s = services_module
    if not s._guest_sessions:
        return
    now = time.time() if now_ts is None else float(now_ts)
    expired = [
        token
        for token, row in s._guest_sessions.items()
        if float(row.get("expires_at", 0.0) or 0.0) <= now
    ]
    for token in expired:
        s._guest_sessions.pop(token, None)
    if expired:
        s._persist_expansion_state()


def resolve_guest_session(
    services_module: Any,
    token: str,
    *,
    now_ts: float | None = None,
) -> dict[str, Any] | None:
    s = services_module
    text = str(token or "").strip()
    if not text:
        return None
    prune_guest_sessions(s, now_ts=now_ts)
    row = s._guest_sessions.get(text)
    if not isinstance(row, dict):
        return None
    expires_at = float(row.get("expires_at", 0.0) or 0.0)
    now = time.time() if now_ts is None else float(now_ts)
    if expires_at <= now:
        s._guest_sessions.pop(text, None)
        return None
    return row


def register_guest_session(
    services_module: Any,
    *,
    guest_id: str,
    capabilities: list[str],
    ttl_sec: float,
    now_ts: float | None = None,
) -> dict[str, Any]:
    s = services_module
    now = time.time() if now_ts is None else float(now_ts)
    ttl = s._as_float(ttl_sec, s.GUEST_SESSION_DEFAULT_TTL_SEC, minimum=60.0, maximum=s.GUEST_SESSION_MAX_TTL_SEC)
    token = secrets.token_urlsafe(12)
    row = {
        "token": token,
        "guest_id": str(guest_id or "guest").strip().lower() or "guest",
        "capabilities": sorted(set(s._as_str_list(capabilities, lower=True))),
        "issued_at": now,
        "expires_at": now + ttl,
    }
    s._guest_sessions[token] = row
    prune_guest_sessions(s, now_ts=now)
    return row
