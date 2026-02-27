"""Webhook and calendar payload runtime helpers for services domains."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse


def collect_json_lists_by_key(value: Any, key: str) -> list[Any]:
    results: list[Any] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key and isinstance(item_value, list):
                results.extend(item_value)
            else:
                results.extend(collect_json_lists_by_key(item_value, key))
    elif isinstance(value, list):
        for item in value:
            results.extend(collect_json_lists_by_key(item, key))
    return results


def parse_calendar_event_timestamp(services_module: Any, value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    parsed = services_module._parse_datetime_text(value)
    if parsed is None:
        return None
    return parsed.timestamp()


def webhook_host_allowed(services_module: Any, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if not services_module._webhook_allowlist:
        return False
    for allowed in services_module._webhook_allowlist:
        if host == allowed:
            return True
        if host.endswith(f".{allowed}"):
            return True
    return False


def record_inbound_webhook_event(
    services_module: Any,
    *,
    payload: Any,
    headers: dict[str, Any] | None = None,
    source: str = "unknown",
    path: str = "/",
) -> int:
    s = services_module
    event_id = s._inbound_webhook_seq
    s._inbound_webhook_seq += 1
    entry = {
        "id": event_id,
        "timestamp": time.time(),
        "source": str(source),
        "path": str(path),
        "headers": s._sanitize_inbound_headers(headers),
        "payload": s._sanitize_inbound_payload(payload),
    }
    s._inbound_webhook_events.append(entry)
    if len(s._inbound_webhook_events) > 500:
        del s._inbound_webhook_events[:-500]
    s._audit(
        "webhook_inbound",
        {
            "result": "ok",
            "event_id": event_id,
            "source": entry["source"],
            "path": entry["path"],
            "header_count": len(entry["headers"]),
        },
    )
    return event_id
