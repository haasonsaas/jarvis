"""Nudge decision handler for proactive assistant."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_proactive_runtime import (
    has_recent_dispatch as _has_recent_dispatch,
    nudge_bucket as _nudge_bucket,
    nudge_fingerprint as _nudge_fingerprint,
    nudge_reason_counts as _nudge_reason_counts,
    nudge_row_score as _nudge_row_score,
    nudge_severity as _nudge_severity,
    prune_recent_dispatches as _prune_recent_dispatches,
    record_recent_dispatch as _record_recent_dispatch,
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
    record_summary = s.record_summary
    _as_float = s._as_float
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response
    _as_int = s._as_int
    _as_bool = s._as_bool
    _normalize_nudge_policy = s._normalize_nudge_policy
    _nudge_policy = s._nudge_policy
    _quiet_window_active = s._quiet_window_active
    NUDGE_RECENT_DISPATCH_MAX = s.NUDGE_RECENT_DISPATCH_MAX

    candidates = args.get("candidates") if isinstance(args.get("candidates"), list) else []
    max_dispatch = _as_int(args.get("max_dispatch", 5), 5, minimum=1, maximum=50)
    now = _as_float(args.get("now", now), now, minimum=0.0)
    dedupe_window_sec = _as_float(args.get("dedupe_window_sec", 600.0), 600.0, minimum=0.0, maximum=86_400.0)
    policy = _normalize_nudge_policy(args.get("policy", _nudge_policy))
    context = args.get("context") if isinstance(args.get("context"), dict) else {}
    user_busy = _as_bool(context.get("user_busy"), default=False)
    conversation_active = _as_bool(context.get("conversation_active"), default=False)
    presence_confidence = _as_float(
        context.get("presence_confidence", 1.0),
        1.0,
        minimum=0.0,
        maximum=1.0,
    )
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
    dedupe_suppressed = 0

    interrupt_rows: list[dict[str, Any]] = []
    notify_rows: list[dict[str, Any]] = []
    defer_rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidates):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("text") or row.get("task") or f"candidate-{index}").strip()
        if not title:
            title = f"candidate-{index}"
        severity, severity_rank = _nudge_severity(row.get("severity"))
        due_at = _as_float(row.get("due_at", 0.0), 0.0, minimum=0.0)
        expires_at = _as_float(row.get("expires_at", 0.0), 0.0, minimum=0.0)
        overdue_sec = max(0.0, now - due_at) if due_at > 0.0 else 0.0
        due_soon_sec = max(0.0, due_at - now) if due_at > 0.0 else 0.0
        bucket, reason = _nudge_bucket(
            policy=policy,
            quiet_active=quiet_active,
            severity_rank=severity_rank,
            overdue_sec=overdue_sec,
            due_soon_sec=due_soon_sec,
        )
        if expires_at > 0.0 and expires_at < now:
            bucket = "defer"
            reason = "expired"
        if bucket == "interrupt" and not _as_bool(row.get("interrupt_allowed"), default=True):
            bucket = "notify" if not quiet_active else "defer"
            reason = "interrupt_not_allowed"
        if bucket == "interrupt":
            if conversation_active and severity_rank < 4 and overdue_sec < 1800.0:
                bucket = "notify" if not quiet_active else "defer"
                reason = "context_conversation_active"
            elif user_busy and severity_rank < 4 and overdue_sec < 1200.0:
                bucket = "notify" if not quiet_active else "defer"
                reason = "context_user_busy"
            elif presence_confidence < 0.35 and severity_rank < 4:
                bucket = "notify" if not quiet_active else "defer"
                reason = "context_low_presence_confidence"
        source = str(row.get("source", "unknown")).strip() or "unknown"
        fingerprint = _nudge_fingerprint(
            row=row,
            title=title,
            severity=severity,
            source=source,
        )
        if bucket in {"interrupt", "notify"} and _has_recent_dispatch(
            recent_dispatches,
            fingerprint=fingerprint,
            now_ts=now,
            dedupe_window_sec=dedupe_window_sec,
        ):
            bucket = "defer"
            reason = "duplicate_recent_dispatch"
            dedupe_suppressed += 1
        item = {
            "id": str(row.get("id", f"nudge-{index}")).strip() or f"nudge-{index}",
            "title": title,
            "severity": severity,
            "source": source,
            "overdue_sec": overdue_sec,
            "due_soon_sec": due_soon_sec,
            "score": _nudge_row_score(
                severity_rank=severity_rank,
                overdue_sec=overdue_sec,
                due_soon_sec=due_soon_sec,
            ),
            "bucket": bucket,
            "reason": reason,
            "_fingerprint": fingerprint,
        }
        if bucket == "interrupt":
            interrupt_rows.append(item)
        elif bucket == "notify":
            notify_rows.append(item)
        else:
            defer_rows.append(item)

    interrupt_rows.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
    notify_rows.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
    defer_rows.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
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
            "user_busy": user_busy,
            "conversation_active": conversation_active,
            "presence_confidence": presence_confidence,
        },
        "candidate_count": len(candidates),
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
