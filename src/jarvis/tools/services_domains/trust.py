"""Proactive assistant domain handlers extracted from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.trust_proactive_briefing import (
    proactive_briefing,
    proactive_event_digest,
)
from jarvis.tools.services_domains.trust_proactive_followthrough import (
    proactive_follow_through,
    proactive_routine_suggestions,
)
from jarvis.tools.services_domains.trust_proactive_nudges import (
    proactive_anomaly_scan,
    proactive_nudge_decision,
)


def _services():
    from jarvis.tools import services as s

    return s


async def proactive_assistant(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("proactive_assistant"):
        record_summary("proactive_assistant", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    action = str(args.get("action", "")).strip().lower()
    now = time.time()

    if action == "briefing":
        return await proactive_briefing(args, now=now, start_time=start_time)
    if action == "anomaly_scan":
        return await proactive_anomaly_scan(args, now=now, start_time=start_time)
    if action == "nudge_decision":
        return await proactive_nudge_decision(args, now=now, start_time=start_time)
    if action == "routine_suggestions":
        return await proactive_routine_suggestions(args, start_time=start_time)
    if action == "follow_through":
        return await proactive_follow_through(args, now=now, start_time=start_time)
    if action == "event_digest":
        return await proactive_event_digest(args, now=now, start_time=start_time)

    _record_service_error("proactive_assistant", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown proactive_assistant action."}]}
