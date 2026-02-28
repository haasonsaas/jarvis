"""Routine suggestion and follow-through handlers for proactive assistant."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _priority_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"critical", "high", "medium", "low"}:
        return normalized
    return "medium"


def _priority_rank(priority: str) -> int:
    normalized = str(priority or "").strip().lower()
    if normalized == "critical":
        return 4
    if normalized == "high":
        return 3
    if normalized == "medium":
        return 2
    return 1


async def proactive_routine_suggestions(
    args: dict[str, Any],
    *,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_bool = s._as_bool
    _as_float = s._as_float
    _parse_due_timestamp = s._parse_due_timestamp
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response

    if not _as_bool(args.get("opt_in"), default=False):
        _record_service_error("proactive_assistant", start_time, "policy")
        return {"content": [{"type": "text", "text": "Routine suggestions require opt_in=true."}]}
    history = args.get("history") if isinstance(args.get("history"), list) else []
    counts: dict[str, int] = {}
    timestamps: dict[str, list[float]] = {}
    now = float(s.time.time())
    for row in history:
        if isinstance(row, dict):
            key = str(row.get("action") or row.get("name") or "").strip().lower()
            ts = _as_float(row.get("timestamp", row.get("ts", 0.0)), 0.0, minimum=0.0)
            if ts <= 0.0:
                ts = float(_parse_due_timestamp(row.get("at"), now_ts=now) or 0.0)
        else:
            key = str(row).strip().lower()
            ts = 0.0
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if ts > 0.0:
            timestamps.setdefault(key, []).append(ts)
    suggestions = [
        {
            "suggestion": f"Automate '{name}' as a routine trigger.",
            "occurrences": count,
            "confidence": "high" if count >= 6 else ("medium" if count >= 4 else "low"),
            "avg_interval_hours": (
                round(
                    sum(
                        max(0.0, b - a)
                        for a, b in zip(sorted(timestamps.get(name, [])), sorted(timestamps.get(name, []))[1:])
                    )
                    / max(1, len(sorted(timestamps.get(name, []))) - 1)
                    / 3600.0,
                    2,
                )
                if len(timestamps.get(name, [])) >= 2
                else None
            ),
        }
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 3
    ][:10]
    payload = {
        "action": "routine_suggestions",
        "opt_in": True,
        "history_count": len(history),
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }
    record_summary("proactive_assistant", "ok", start_time, effect=f"suggestions={len(suggestions)}", risk="low")
    return _expansion_payload_response(payload)


async def proactive_follow_through(
    args: dict[str, Any],
    *,
    now: float,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_bool = s._as_bool
    _as_float = s._as_float
    _as_int = s._as_int
    _parse_due_timestamp = s._parse_due_timestamp
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response

    queue = _proactive_state.get("pending_follow_through")
    if not isinstance(queue, list):
        queue = []
        _proactive_state["pending_follow_through"] = queue
    max_queue = _as_int(args.get("max_queue", 300), 300, minimum=10, maximum=2000)
    dedupe_window_sec = _as_float(args.get("dedupe_window_sec", 86_400.0), 86_400.0, minimum=0.0, maximum=604_800.0)
    pending = args.get("pending_actions") if isinstance(args.get("pending_actions"), list) else []
    existing_fingerprints: set[str] = set()
    if dedupe_window_sec > 0.0:
        cutoff = max(0.0, now - dedupe_window_sec)
        for row in queue:
            if not isinstance(row, dict):
                continue
            created_at = _as_float(row.get("created_at", 0.0), 0.0, minimum=0.0)
            if created_at < cutoff:
                continue
            fingerprint = str(row.get("fingerprint", "")).strip().lower()
            if fingerprint:
                existing_fingerprints.add(fingerprint)
    enqueued_count = 0
    deduped_count = 0
    invalid_count = 0
    for row in pending:
        if not isinstance(row, dict):
            invalid_count += 1
            continue
        task = str(row.get("task") or row.get("action") or row.get("title") or "").strip()
        if not task:
            invalid_count += 1
            continue
        priority = _priority_label(row.get("priority", row.get("severity", "medium")))
        due_at = _as_float(row.get("due_at", 0.0), 0.0, minimum=0.0)
        if due_at <= 0.0:
            due_at = float(_parse_due_timestamp(row.get("due"), now_ts=now) or 0.0)
        fingerprint = " ".join(task.lower().split())
        if dedupe_window_sec > 0.0 and fingerprint in existing_fingerprints:
            deduped_count += 1
            continue
        existing_fingerprints.add(fingerprint)
        seq = _as_int(_proactive_state.get("follow_through_seq", 1), 1, minimum=1)
        _proactive_state["follow_through_seq"] = seq + 1
        entry = {
            "id": str(row.get("id", "")).strip() or f"follow-{seq}",
            "created_at": now,
            "task": task,
            "priority": priority,
            "due_at": due_at,
            "status": "pending",
            "fingerprint": fingerprint,
            "payload": {str(k): v for k, v in row.items()},
        }
        queue.append(entry)
        enqueued_count += 1
    pruned_count = 0
    if len(queue) > max_queue:
        pruned_count = len(queue) - max_queue
        del queue[:pruned_count]

    confirm = _as_bool(args.get("confirm"), default=False)
    max_dispatch = _as_int(args.get("max_dispatch", 1), 1, minimum=1, maximum=25)
    execute_index = _as_int(args.get("execute_index", -1), -1, minimum=-1, maximum=max(-1, len(queue) - 1))
    selected_indices: list[int] = []
    if confirm and queue:
        if execute_index >= 0:
            selected_indices = [execute_index]
        else:
            ranked = sorted(
                enumerate(queue),
                key=lambda pair: (
                    -_priority_rank(str(pair[1].get("priority", "medium"))),
                    float(pair[1].get("due_at", 0.0) or 0.0) <= 0.0,
                    float(pair[1].get("due_at", now + 100_000_000.0) or now + 100_000_000.0),
                    float(pair[1].get("created_at", now) or now),
                ),
            )
            selected_indices = [index for index, _ in ranked[:max_dispatch]]
    selected_order = [index for index in selected_indices if 0 <= index < len(queue)]
    selected_set = set(selected_order)
    removed_by_index: dict[int, dict[str, Any]] = {}
    for index in sorted(selected_set, reverse=True):
        row = queue.pop(index)
        row["status"] = "completed"
        row["executed_at"] = now
        removed_by_index[index] = row
    executed_items = [removed_by_index[index] for index in selected_order if index in removed_by_index]
    executed = executed_items[0] if executed_items else None

    _proactive_state["follow_through_enqueued_total"] = int(_proactive_state.get("follow_through_enqueued_total", 0) or 0) + enqueued_count
    _proactive_state["follow_through_executed_total"] = int(_proactive_state.get("follow_through_executed_total", 0) or 0) + len(executed_items)
    _proactive_state["follow_through_deduped_total"] = int(_proactive_state.get("follow_through_deduped_total", 0) or 0) + deduped_count
    _proactive_state["follow_through_pruned_total"] = int(_proactive_state.get("follow_through_pruned_total", 0) or 0) + pruned_count
    _proactive_state["last_follow_through_at"] = now

    payload = {
        "action": "follow_through",
        "queue_size": len(queue),
        "confirm": confirm,
        "enqueued_count": enqueued_count,
        "deduped_count": deduped_count,
        "invalid_count": invalid_count,
        "pruned_count": pruned_count,
        "executed_count": len(executed_items),
        "executed": executed,
        "executed_items": executed_items[:20],
        "queue_preview": [dict(row) for row in queue[:20] if isinstance(row, dict)],
        "counters": {
            "follow_through_enqueued_total": int(_proactive_state.get("follow_through_enqueued_total", 0) or 0),
            "follow_through_executed_total": int(_proactive_state.get("follow_through_executed_total", 0) or 0),
            "follow_through_deduped_total": int(_proactive_state.get("follow_through_deduped_total", 0) or 0),
            "follow_through_pruned_total": int(_proactive_state.get("follow_through_pruned_total", 0) or 0),
            "last_follow_through_at": float(_proactive_state.get("last_follow_through_at", 0.0) or 0.0),
        },
    }
    risk = "medium" if len(executed_items) > 0 else "low"
    record_summary(
        "proactive_assistant",
        "ok",
        start_time,
        effect=f"follow_through:queued={len(queue)}:executed={len(executed_items)}",
        risk=risk,
    )
    return _expansion_payload_response(payload)
