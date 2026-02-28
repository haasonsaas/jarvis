"""Briefing and digest handlers for proactive assistant."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _severity_rank(value: str) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "critical":
        return 4
    if normalized == "high":
        return 3
    if normalized == "medium":
        return 2
    return 1


async def proactive_briefing(
    args: dict[str, Any],
    *,
    now: float,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _as_int = s._as_int
    _parse_due_timestamp = s._parse_due_timestamp
    _parse_calendar_event_timestamp = s._parse_calendar_event_timestamp
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response

    mode = str(args.get("mode", "morning")).strip().lower() or "morning"
    if mode not in {"morning", "evening"}:
        mode = "custom"
    calendar = args.get("calendar") if isinstance(args.get("calendar"), list) else []
    reminders = args.get("reminders") if isinstance(args.get("reminders"), list) else []
    weather = args.get("weather") if isinstance(args.get("weather"), dict) else {}
    home_state = args.get("home_state") if isinstance(args.get("home_state"), dict) else {}
    normalized_events: list[dict[str, Any]] = []
    for index, row in enumerate(calendar):
        if not isinstance(row, dict):
            continue
        title = str(row.get("summary") or row.get("title") or row.get("name") or "").strip()
        start_ts = _as_float(row.get("start_ts", 0.0), 0.0, minimum=0.0)
        if start_ts <= 0.0:
            for key in ("start", "start_at", "when", "time"):
                parsed = _parse_calendar_event_timestamp(row.get(key))
                if parsed is not None:
                    start_ts = parsed
                    break
        if not title and start_ts <= 0.0:
            continue
        normalized_events.append(
            {
                "id": str(row.get("id", f"event-{index}")).strip() or f"event-{index}",
                "title": title or f"event-{index}",
                "start_ts": start_ts,
            }
        )
    normalized_events.sort(
        key=lambda item: (
            float(item.get("start_ts", 0.0)) <= 0.0,
            float(item.get("start_ts", now + 10_000_000.0)),
            str(item.get("title", "")),
        )
    )
    next_event_row = next(
        (row for row in normalized_events if float(row.get("start_ts", 0.0)) >= max(0.0, now - 60.0)),
        normalized_events[0] if normalized_events else None,
    )
    due_reminders = 0
    overdue_reminders = 0
    due_soon_reminders = 0
    completed_status = {"completed", "done", "cancelled"}
    for row in reminders:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "pending")).strip().lower() in completed_status:
            continue
        due_at = _as_float(row.get("due_at", 0.0), 0.0, minimum=0.0)
        if due_at <= 0.0:
            due_at = float(
                _parse_due_timestamp(row.get("due"), now_ts=now)
                or _parse_due_timestamp(row.get("due_text"), now_ts=now)
                or 0.0
            )
        if due_at <= now:
            due_reminders += 1
            overdue_reminders += 1
        elif due_at <= (now + 3600.0):
            due_soon_reminders += 1
    next_event = str(next_event_row.get("title", "")).strip() if isinstance(next_event_row, dict) else ""
    next_event_at = float(next_event_row.get("start_ts", 0.0) or 0.0) if isinstance(next_event_row, dict) else 0.0
    weather_text = str(weather.get("summary") or weather.get("condition") or "No weather update").strip()
    if isinstance(home_state.get("alerts"), list):
        home_alerts = len(home_state.get("alerts", []))
    elif isinstance(home_state.get("alerts"), dict):
        alerts_map = home_state.get("alerts", {})
        if isinstance(alerts_map.get("count"), int):
            home_alerts = int(alerts_map.get("count", 0))
        else:
            home_alerts = sum(1 for value in alerts_map.values() if bool(value))
    else:
        home_alerts = _as_int(home_state.get("alerts", 0), 0, minimum=0) if isinstance(home_state, dict) else 0
    briefing_lines: list[str] = []
    if next_event:
        if next_event_at > 0.0:
            delta_minutes = int(max(0.0, next_event_at - now) // 60)
            if delta_minutes == 0:
                briefing_lines.append(f"Next event: {next_event} is starting now.")
            else:
                briefing_lines.append(f"Next event: {next_event} in about {delta_minutes} minutes.")
        else:
            briefing_lines.append(f"Next event: {next_event}.")
    else:
        briefing_lines.append("No upcoming calendar events found.")
    briefing_lines.append(
        f"Reminders: {due_reminders} due now, {due_soon_reminders} due within the next hour."
    )
    briefing_lines.append(f"Weather: {weather_text}.")
    if home_alerts > 0:
        briefing_lines.append(f"Home alerts: {home_alerts} active.")

    _proactive_state["briefings_total"] = int(_proactive_state.get("briefings_total", 0) or 0) + 1
    _proactive_state["last_briefing_mode"] = mode
    _proactive_state["last_briefing_at"] = now
    payload = {
        "action": "briefing",
        "mode": mode,
        "next_event": next_event,
        "next_event_at": next_event_at,
        "calendar_items": len(calendar),
        "due_reminders": due_reminders,
        "overdue_reminders": overdue_reminders,
        "due_soon_reminders": due_soon_reminders,
        "weather": weather_text,
        "home_alerts": home_alerts,
        "generated_at": now,
        "briefing_lines": briefing_lines[:6],
        "counters": {
            "briefings_total": int(_proactive_state.get("briefings_total", 0) or 0),
            "last_briefing_mode": str(_proactive_state.get("last_briefing_mode", "")),
        },
        "briefing": (
            f"{mode.title()} briefing: " + " ".join(briefing_lines[:4])
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
            "digest_count": len(digest_items),
        }
        record_summary("proactive_assistant", "ok", start_time, effect="digest_snoozed", risk="low")
        return _expansion_payload_response(payload)
    max_dispatch = _as_int(args.get("max_dispatch", 20), 20, minimum=1, maximum=100)
    seen_keys: set[str] = set()
    normalized_items: list[dict[str, Any]] = []
    deduped_count = 0
    for index, row in enumerate(digest_items):
        if isinstance(row, dict):
            title = str(row.get("title") or row.get("summary") or row.get("message") or row.get("text") or "").strip()
            source = str(row.get("source", "digest")).strip().lower() or "digest"
            severity = str(row.get("severity", "low")).strip().lower() or "low"
            item_id = str(row.get("id", "")).strip() or f"digest-{index}"
            due_at = float(s._as_float(row.get("due_at", 0.0), 0.0, minimum=0.0))
        else:
            title = str(row).strip()
            source = "digest"
            severity = "low"
            item_id = f"digest-{index}"
            due_at = 0.0
        if not title:
            title = f"digest-item-{index}"
        key = f"{item_id.lower()}|{source}|{title.lower()}"
        if key in seen_keys:
            deduped_count += 1
            continue
        seen_keys.add(key)
        normalized_items.append(
            {
                "id": item_id,
                "title": title,
                "source": source,
                "severity": severity if severity in {"low", "medium", "high", "critical"} else "low",
                "due_at": due_at,
            }
        )
    normalized_items.sort(
        key=lambda row: (
            -_severity_rank(str(row.get("severity", "low"))),
            float(row.get("due_at", 0.0) or 0.0) <= 0.0,
            float(row.get("due_at", 0.0) or 0.0),
            str(row.get("title", "")),
        )
    )
    dispatch_items = normalized_items[:max_dispatch]
    deferred_items = normalized_items[max_dispatch:]
    _proactive_state["digests_total"] = int(_proactive_state.get("digests_total", 0) or 0) + 1
    _proactive_state["digest_items_total"] = int(_proactive_state.get("digest_items_total", 0) or 0) + len(dispatch_items)
    _proactive_state["digest_deduped_total"] = int(_proactive_state.get("digest_deduped_total", 0) or 0) + deduped_count
    payload = {
        "action": "event_digest",
        "status": "ready",
        "digest_count": len(dispatch_items),
        "total_candidates": len(normalized_items),
        "deferred_count": len(deferred_items),
        "deduped_count": deduped_count,
        "digest_items": dispatch_items[:20],
        "deferred_items": deferred_items[:20],
        "max_dispatch": max_dispatch,
        "snoozed_until": snoozed_until,
        "counters": {
            "digests_total": int(_proactive_state.get("digests_total", 0) or 0),
            "digest_items_total": int(_proactive_state.get("digest_items_total", 0) or 0),
            "digest_deduped_total": int(_proactive_state.get("digest_deduped_total", 0) or 0),
        },
    }
    record_summary("proactive_assistant", "ok", start_time, effect="digest_ready", risk="low")
    return _expansion_payload_response(payload)
