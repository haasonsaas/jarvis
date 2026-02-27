"""Policy and guest-session helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

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


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def normalize_nudge_policy(value: Any) -> str:
    return _runtime_normalize_nudge_policy(value)


def hhmm_to_minutes(value: str) -> int | None:
    return _runtime_hhmm_to_minutes(value)


def quiet_window_active(*, now_ts: float | None = None) -> bool:
    return _runtime_quiet_window_active(_services_module(), now_ts=now_ts)


def identity_profile_level(profile: str) -> str:
    return _runtime_identity_profile_level(profile)


def profile_rank(profile: str) -> int:
    return _runtime_profile_rank(profile)


def prune_guest_sessions(*, now_ts: float | None = None) -> None:
    _runtime_prune_guest_sessions(_services_module(), now_ts=now_ts)


def resolve_guest_session(token: str, *, now_ts: float | None = None) -> dict[str, Any] | None:
    return _runtime_resolve_guest_session(_services_module(), token, now_ts=now_ts)


def register_guest_session(
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
