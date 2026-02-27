"""Inbound webhook event list/clear handlers."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def webhook_inbound_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _inbound_webhook_events = s._inbound_webhook_events
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_list"):
        record_summary("webhook_inbound_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    rows = list(reversed(_inbound_webhook_events))[:limit]
    record_summary("webhook_inbound_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(rows, default=str)}]}


async def webhook_inbound_clear(args: dict[str, Any]) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _inbound_webhook_events = s._inbound_webhook_events
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_clear"):
        record_summary("webhook_inbound_clear", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    count = len(_inbound_webhook_events)
    _inbound_webhook_events.clear()
    record_summary("webhook_inbound_clear", "ok", start_time)
    _audit("webhook_inbound_clear", {"result": "ok", "cleared_count": count})
    return {"content": [{"type": "text", "text": f"Cleared inbound webhook events: {count}."}]}
