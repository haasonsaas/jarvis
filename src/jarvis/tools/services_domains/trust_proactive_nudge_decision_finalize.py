"""Dispatch and payload finalization for proactive nudge decisions."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_proactive_runtime import (
    nudge_reason_counts as _nudge_reason_counts,
    prune_recent_dispatches as _prune_recent_dispatches,
    record_recent_dispatch as _record_recent_dispatch,
)


def _services():
    from jarvis.tools import services as s

    return s


def proactive_nudge_finalize(
    *,
    classification: dict[str, Any],
    max_dispatch: int,
    now: float,
    dedupe_window_sec: float,
    policy: str,
    quiet_active: bool,
    recent_dispatches: list[dict[str, Any]],
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response
    NUDGE_RECENT_DISPATCH_MAX = s.NUDGE_RECENT_DISPATCH_MAX

    interrupt_rows = classification.get("interrupt_rows") if isinstance(classification.get("interrupt_rows"), list) else []
    notify_rows = classification.get("notify_rows") if isinstance(classification.get("notify_rows"), list) else []
    defer_rows = classification.get("defer_rows") if isinstance(classification.get("defer_rows"), list) else []
    dedupe_suppressed = int(classification.get("dedupe_suppressed", 0) or 0)
    candidate_count = int(classification.get("candidate_count", 0) or 0)
    context = classification.get("context") if isinstance(classification.get("context"), dict) else {}

    dispatch_rows = interrupt_rows + notify_rows
    overflow = dispatch_rows[max_dispatch:]
    dispatch_rows = dispatch_rows[:max_dispatch]
    if overflow:
        for row in overflow:
            row["bucket"] = "defer"
            row["reason"] = "dispatch_capacity"
        defer_rows.extend(overflow)
    interrupt = [row for row in dispatch_rows if str(row.get("bucket", "")) == "interrupt"]
    notify = [row for row in dispatch_rows if str(row.get("bucket", "")) == "notify"]

    for row in interrupt + notify:
        _record_recent_dispatch(
            recent_dispatches,
            fingerprint=str(row.get("_fingerprint", "")),
            dispatched_at=now,
        )
    recent_dispatches = _prune_recent_dispatches(
        recent_dispatches,
        now_ts=now,
        dedupe_window_sec=dedupe_window_sec,
        max_entries=NUDGE_RECENT_DISPATCH_MAX,
    )
    for row in interrupt:
        row.pop("bucket", None)
        row.pop("_fingerprint", None)
    for row in notify:
        row.pop("bucket", None)
        row.pop("_fingerprint", None)
    for row in defer_rows:
        row.pop("bucket", None)
        row.pop("_fingerprint", None)

    _proactive_state["nudge_decisions_total"] = int(_proactive_state.get("nudge_decisions_total", 0) or 0) + 1
    _proactive_state["nudge_interrupt_total"] = int(_proactive_state.get("nudge_interrupt_total", 0) or 0) + len(interrupt)
    _proactive_state["nudge_notify_total"] = int(_proactive_state.get("nudge_notify_total", 0) or 0) + len(notify)
    _proactive_state["nudge_defer_total"] = int(_proactive_state.get("nudge_defer_total", 0) or 0) + len(defer_rows)
    _proactive_state["nudge_deduped_total"] = int(_proactive_state.get("nudge_deduped_total", 0) or 0) + dedupe_suppressed
    _proactive_state["last_nudge_decision_at"] = now
    if dedupe_suppressed > 0:
        _proactive_state["last_nudge_dedupe_at"] = now
    _proactive_state["nudge_recent_dispatches"] = recent_dispatches

    payload = {
        "action": "nudge_decision",
        "policy": policy,
        "quiet_window_active": quiet_active,
        "context": {
            "user_busy": bool(context.get("user_busy", False)),
            "conversation_active": bool(context.get("conversation_active", False)),
            "presence_confidence": float(context.get("presence_confidence", 1.0) or 1.0),
        },
        "candidate_count": candidate_count,
        "dispatch_count": len(dispatch_rows),
        "interrupt_count": len(interrupt),
        "notify_count": len(notify),
        "defer_count": len(defer_rows),
        "dedupe_window_sec": dedupe_window_sec,
        "dedupe_suppressed_count": dedupe_suppressed,
        "reason_counts": _nudge_reason_counts(
            interrupt=interrupt,
            notify=notify,
            defer=defer_rows,
        ),
        "interrupt": interrupt,
        "notify": notify,
        "defer": defer_rows,
        "counters": {
            "nudge_decisions_total": int(_proactive_state.get("nudge_decisions_total", 0) or 0),
            "nudge_interrupt_total": int(_proactive_state.get("nudge_interrupt_total", 0) or 0),
            "nudge_notify_total": int(_proactive_state.get("nudge_notify_total", 0) or 0),
            "nudge_defer_total": int(_proactive_state.get("nudge_defer_total", 0) or 0),
            "nudge_deduped_total": int(_proactive_state.get("nudge_deduped_total", 0) or 0),
            "last_nudge_decision_at": float(_proactive_state.get("last_nudge_decision_at", 0.0) or 0.0),
            "last_nudge_dedupe_at": float(_proactive_state.get("last_nudge_dedupe_at", 0.0) or 0.0),
            "nudge_recent_dispatch_count": len(recent_dispatches),
        },
    }
    risk = "medium" if interrupt else ("low" if not notify else "medium")
    record_summary(
        "proactive_assistant",
        "ok",
        start_time,
        effect=f"nudge_dispatch={len(dispatch_rows)}",
        risk=risk,
    )
    return _expansion_payload_response(payload)
