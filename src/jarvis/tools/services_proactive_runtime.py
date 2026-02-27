"""Proactive nudge scoring and dedupe helpers."""

from __future__ import annotations

from typing import Any


def nudge_severity(value: Any) -> tuple[str, int]:
    text = str(value or "").strip().lower()
    if text == "critical":
        return "critical", 4
    if text == "high":
        return "high", 3
    if text == "medium":
        return "medium", 2
    return "low", 1


def nudge_row_score(*, severity_rank: int, overdue_sec: float, due_soon_sec: float) -> float:
    overdue_weight = min(7200.0, max(0.0, overdue_sec)) * 0.02
    due_weight = 0.0
    if due_soon_sec > 0.0:
        due_weight = max(0.0, 900.0 - min(900.0, due_soon_sec)) * 0.01
    return float(severity_rank * 100.0) + overdue_weight + due_weight


def nudge_bucket(
    *,
    policy: str,
    quiet_active: bool,
    severity_rank: int,
    overdue_sec: float,
    due_soon_sec: float,
) -> tuple[str, str]:
    if policy == "defer":
        if severity_rank >= 4 or overdue_sec >= 3600.0:
            return "interrupt", "critical_or_overdue"
        return "defer", "policy_defer"
    if policy == "interrupt":
        if quiet_active and severity_rank <= 2 and overdue_sec < 600.0:
            return "notify", "quiet_window_softened"
        if severity_rank >= 2 or overdue_sec >= 300.0:
            return "interrupt", "policy_interrupt"
        return "notify", "policy_interrupt_soft"

    if quiet_active:
        if severity_rank >= 4 or overdue_sec >= 1800.0:
            return "interrupt", "quiet_escalation"
        if severity_rank >= 3 or overdue_sec >= 600.0:
            return "notify", "quiet_notify"
        return "defer", "quiet_defer"
    if severity_rank >= 3 or overdue_sec >= 300.0:
        return "interrupt", "adaptive_interrupt"
    if severity_rank >= 2 or due_soon_sec <= 900.0:
        return "notify", "adaptive_notify"
    return "defer", "adaptive_defer"


def nudge_fingerprint(*, row: dict[str, Any], title: str, severity: str, source: str) -> str:
    candidate_id = str(row.get("id", "")).strip().lower()
    if candidate_id:
        return f"id:{candidate_id}"
    normalized_title = " ".join(title.strip().lower().split())
    normalized_source = " ".join(source.strip().lower().split())
    normalized_severity = " ".join(severity.strip().lower().split()) or "low"
    return (
        f"title:{normalized_title}|source:{normalized_source}|severity:{normalized_severity}"
    )


def prune_recent_dispatches(
    rows: Any,
    *,
    now_ts: float,
    dedupe_window_sec: float,
    max_entries: int,
) -> list[dict[str, Any]]:
    if dedupe_window_sec <= 0.0 or max_entries <= 0:
        return []
    if not isinstance(rows, list):
        return []
    cutoff = max(0.0, now_ts - dedupe_window_sec)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fingerprint = str(row.get("fingerprint", "")).strip()
        if not fingerprint:
            continue
        raw_dispatched_at = row.get("dispatched_at", 0.0)
        try:
            dispatched_at = float(raw_dispatched_at or 0.0)
        except Exception:
            dispatched_at = 0.0
        if dispatched_at < cutoff:
            continue
        normalized.append({"fingerprint": fingerprint, "dispatched_at": dispatched_at})
    normalized.sort(key=lambda item: (float(item.get("dispatched_at", 0.0)), str(item.get("fingerprint", ""))))
    if len(normalized) > max_entries:
        normalized = normalized[-max_entries:]
    return normalized


def has_recent_dispatch(
    rows: list[dict[str, Any]],
    *,
    fingerprint: str,
    now_ts: float,
    dedupe_window_sec: float,
) -> bool:
    if dedupe_window_sec <= 0.0 or not fingerprint:
        return False
    cutoff = max(0.0, now_ts - dedupe_window_sec)
    for row in reversed(rows):
        if str(row.get("fingerprint", "")) != fingerprint:
            continue
        try:
            dispatched_at = float(row.get("dispatched_at", 0.0) or 0.0)
        except Exception:
            dispatched_at = 0.0
        if dispatched_at >= cutoff:
            return True
    return False


def record_recent_dispatch(rows: list[dict[str, Any]], *, fingerprint: str, dispatched_at: float) -> None:
    if not fingerprint:
        return
    rows.append({"fingerprint": fingerprint, "dispatched_at": float(dispatched_at)})


def nudge_reason_counts(*, interrupt: list[dict[str, Any]], notify: list[dict[str, Any]], defer: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in interrupt + notify + defer:
        reason = str(row.get("reason", "unknown")).strip().lower() or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return {name: counts[name] for name in sorted(counts)}
