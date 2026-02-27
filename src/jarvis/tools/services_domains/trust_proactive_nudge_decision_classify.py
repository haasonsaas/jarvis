"""Candidate classification for proactive nudge decisions."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_proactive_runtime import (
    has_recent_dispatch as _has_recent_dispatch,
    nudge_bucket as _nudge_bucket,
    nudge_fingerprint as _nudge_fingerprint,
    nudge_row_score as _nudge_row_score,
    nudge_severity as _nudge_severity,
)


def _services():
    from jarvis.tools import services as s

    return s


def proactive_nudge_classify_candidates(
    *,
    args: dict[str, Any],
    now: float,
    policy: str,
    quiet_active: bool,
    recent_dispatches: list[dict[str, Any]],
    dedupe_window_sec: float,
) -> dict[str, Any]:
    s = _services()
    _as_float = s._as_float
    _as_bool = s._as_bool

    candidates = args.get("candidates") if isinstance(args.get("candidates"), list) else []
    context = args.get("context") if isinstance(args.get("context"), dict) else {}
    user_busy = _as_bool(context.get("user_busy"), default=False)
    conversation_active = _as_bool(context.get("conversation_active"), default=False)
    presence_confidence = _as_float(
        context.get("presence_confidence", 1.0),
        1.0,
        minimum=0.0,
        maximum=1.0,
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

    return {
        "candidate_count": len(candidates),
        "context": {
            "user_busy": user_busy,
            "conversation_active": conversation_active,
            "presence_confidence": presence_confidence,
        },
        "dedupe_suppressed": dedupe_suppressed,
        "interrupt_rows": interrupt_rows,
        "notify_rows": notify_rows,
        "defer_rows": defer_rows,
    }
