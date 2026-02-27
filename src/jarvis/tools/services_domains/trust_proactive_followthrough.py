"""Routine suggestion and follow-through handlers for proactive assistant."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def proactive_routine_suggestions(
    args: dict[str, Any],
    *,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_bool = s._as_bool
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response

    if not _as_bool(args.get("opt_in"), default=False):
        _record_service_error("proactive_assistant", start_time, "policy")
        return {"content": [{"type": "text", "text": "Routine suggestions require opt_in=true."}]}
    history = args.get("history") if isinstance(args.get("history"), list) else []
    counts: dict[str, int] = {}
    for row in history:
        if isinstance(row, dict):
            key = str(row.get("action") or row.get("name") or "").strip().lower()
        else:
            key = str(row).strip().lower()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    suggestions = [
        {
            "suggestion": f"Automate '{name}' as a routine trigger.",
            "occurrences": count,
        }
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 3
    ][:10]
    payload = {
        "action": "routine_suggestions",
        "opt_in": True,
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
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response

    pending = args.get("pending_actions") if isinstance(args.get("pending_actions"), list) else []
    for row in pending:
        if not isinstance(row, dict):
            continue
        _proactive_state["pending_follow_through"].append(
            {
                "created_at": now,
                "task": str(row.get("task") or row.get("action") or "").strip(),
                "payload": {str(k): v for k, v in row.items()},
            }
        )
    executed: dict[str, Any] | None = None
    if _as_bool(args.get("confirm"), default=False) and _proactive_state["pending_follow_through"]:
        executed = _proactive_state["pending_follow_through"].pop(0)
        executed["executed_at"] = now
    payload = {
        "action": "follow_through",
        "queue_size": len(_proactive_state["pending_follow_through"]),
        "executed": executed,
    }
    record_summary("proactive_assistant", "ok", start_time, effect="follow_through", risk="low")
    return _expansion_payload_response(payload)
