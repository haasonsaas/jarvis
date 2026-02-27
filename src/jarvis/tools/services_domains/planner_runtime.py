"""Planner domain runtime helpers."""

from __future__ import annotations

from typing import Any


def _reminder_row_payload(row: Any) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "text": str(row.text),
        "due_at": float(row.due_at),
        "created_at": float(row.created_at),
        "status": str(row.status),
        "completed_at": float(row.completed_at) if row.completed_at is not None else None,
        "notified_at": float(row.notified_at) if row.notified_at is not None else None,
    }


def list_reminder_payloads(
    *,
    memory: Any | None,
    reminders: dict[int, dict[str, Any]],
    include_completed: bool,
    limit: int,
    now_ts: float,
) -> list[dict[str, Any]]:
    if memory is not None:
        pending_rows = memory.list_reminders(status="pending", now=now_ts, limit=limit)
        completed_rows = memory.list_reminders(status="completed", limit=limit) if include_completed else []
        payloads = [_reminder_row_payload(row) for row in [*pending_rows, *completed_rows]]
    else:
        payloads = list(reminders.values())
        if not include_completed:
            payloads = [payload for payload in payloads if str(payload.get("status", "pending")) == "pending"]
    payloads = sorted(payloads, key=lambda payload: float(payload.get("due_at", now_ts)))
    return payloads[:limit]


def due_unnotified_reminder_payloads(
    *,
    memory: Any | None,
    reminders: dict[int, dict[str, Any]],
    limit: int,
    now_ts: float,
) -> list[dict[str, Any]]:
    if memory is not None:
        rows = memory.list_reminders(
            status="pending",
            due_only=True,
            include_notified=False,
            now=now_ts,
            limit=limit,
        )
        return [_reminder_row_payload(row) for row in rows]
    rows = [
        payload
        for payload in reminders.values()
        if str(payload.get("status", "pending")) == "pending"
        and float(payload.get("due_at", now_ts + 1.0)) <= now_ts
        and payload.get("notified_at") is None
    ]
    rows = sorted(rows, key=lambda payload: float(payload.get("due_at", now_ts)))
    return rows[:limit]
