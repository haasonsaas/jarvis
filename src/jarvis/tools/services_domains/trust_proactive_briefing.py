"""Briefing and digest handlers for proactive assistant."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def proactive_briefing(
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

    mode = str(args.get("mode", "morning")).strip().lower() or "morning"
    calendar = args.get("calendar") if isinstance(args.get("calendar"), list) else []
    reminders = args.get("reminders") if isinstance(args.get("reminders"), list) else []
    weather = args.get("weather") if isinstance(args.get("weather"), dict) else {}
    home_state = args.get("home_state") if isinstance(args.get("home_state"), dict) else {}
    due_reminders = 0
    for row in reminders:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "pending")).strip().lower() == "completed":
            continue
        due_at = _as_float(row.get("due_at", row.get("due", now + 1_000_000)), now + 1_000_000)
        if due_at <= now:
            due_reminders += 1
    next_event = ""
    for row in calendar:
        if isinstance(row, dict):
            next_event = str(row.get("summary") or row.get("title") or "").strip()
            if next_event:
                break
    weather_text = str(weather.get("summary") or weather.get("condition") or "No weather update").strip()
    home_alerts = int(home_state.get("alerts", 0) or 0) if isinstance(home_state, dict) else 0
    _proactive_state["last_briefing_at"] = now
    payload = {
        "action": "briefing",
        "mode": mode,
        "next_event": next_event,
        "calendar_items": len(calendar),
        "due_reminders": due_reminders,
        "weather": weather_text,
        "home_alerts": home_alerts,
        "briefing": (
            f"{mode.title()} briefing: {len(calendar)} calendar items, {due_reminders} due reminders, "
            f"weather '{weather_text}', home alerts={home_alerts}."
        ),
    }
    record_summary("proactive_assistant", "ok", start_time, effect=f"briefing:{mode}", risk="low")
    return _expansion_payload_response(payload)


async def proactive_event_digest(
    args: dict[str, Any],
    *,
    now: float,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_int = s._as_int
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response

    snooze_minutes = _as_int(args.get("snooze_minutes", 0), 0, minimum=0, maximum=24 * 60)
    if snooze_minutes > 0:
        _proactive_state["digest_snoozed_until"] = now + (snooze_minutes * 60.0)
    snoozed_until = float(_proactive_state.get("digest_snoozed_until", 0.0) or 0.0)
    digest_items = args.get("digest_items") if isinstance(args.get("digest_items"), list) else []
    _proactive_state["last_digest_at"] = now
    if snoozed_until > now:
        payload = {
            "action": "event_digest",
            "status": "snoozed",
            "snoozed_until": snoozed_until,
            "remaining_sec": max(0.0, snoozed_until - now),
        }
        record_summary("proactive_assistant", "ok", start_time, effect="digest_snoozed", risk="low")
        return _expansion_payload_response(payload)
    payload = {
        "action": "event_digest",
        "status": "ready",
        "digest_count": len(digest_items),
        "digest_items": digest_items[:20],
        "snoozed_until": snoozed_until,
    }
    record_summary("proactive_assistant", "ok", start_time, effect="digest_ready", risk="low")
    return _expansion_payload_response(payload)
