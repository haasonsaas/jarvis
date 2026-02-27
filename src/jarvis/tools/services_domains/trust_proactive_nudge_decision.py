"""Nudge decision handler for proactive assistant."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.trust_proactive_nudge_decision_classify import (
    proactive_nudge_classify_candidates,
)
from jarvis.tools.services_domains.trust_proactive_nudge_decision_finalize import (
    proactive_nudge_finalize,
)
from jarvis.tools.services_proactive_runtime import (
    prune_recent_dispatches as _prune_recent_dispatches,
)


def _services():
    from jarvis.tools import services as s

    return s


async def proactive_nudge_decision(
    args: dict[str, Any],
    *,
    now: float,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    _as_float = s._as_float
    _proactive_state = s._proactive_state
    _as_int = s._as_int
    _normalize_nudge_policy = s._normalize_nudge_policy
    _nudge_policy = s._nudge_policy
    _quiet_window_active = s._quiet_window_active
    NUDGE_RECENT_DISPATCH_MAX = s.NUDGE_RECENT_DISPATCH_MAX

    max_dispatch = _as_int(args.get("max_dispatch", 5), 5, minimum=1, maximum=50)
    now = _as_float(args.get("now", now), now, minimum=0.0)
    dedupe_window_sec = _as_float(args.get("dedupe_window_sec", 600.0), 600.0, minimum=0.0, maximum=86_400.0)
    policy = _normalize_nudge_policy(args.get("policy", _nudge_policy))
    quiet_override = args.get("quiet_window_active")
    if isinstance(quiet_override, bool):
        quiet_active = quiet_override
    else:
        quiet_active = _quiet_window_active(now_ts=now)

    recent_dispatches = _prune_recent_dispatches(
        _proactive_state.get("nudge_recent_dispatches", []),
        now_ts=now,
        dedupe_window_sec=dedupe_window_sec,
        max_entries=NUDGE_RECENT_DISPATCH_MAX,
    )
    classification = proactive_nudge_classify_candidates(
        args=args,
        now=now,
        policy=policy,
        quiet_active=quiet_active,
        recent_dispatches=recent_dispatches,
        dedupe_window_sec=dedupe_window_sec,
    )
    return proactive_nudge_finalize(
        classification=classification,
        max_dispatch=max_dispatch,
        now=now,
        dedupe_window_sec=dedupe_window_sec,
        policy=policy,
        quiet_active=quiet_active,
        recent_dispatches=recent_dispatches,
        start_time=start_time,
    )
