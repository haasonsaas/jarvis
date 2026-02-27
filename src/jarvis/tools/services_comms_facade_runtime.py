"""Webhook/email helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_email_runtime import (
    record_email_history as _runtime_record_email_history,
    send_email_sync as _runtime_send_email_sync,
)
from jarvis.tools.services_webhook_runtime import (
    collect_json_lists_by_key as _runtime_collect_json_lists_by_key,
    parse_calendar_event_timestamp as _runtime_parse_calendar_event_timestamp,
    record_inbound_webhook_event as _runtime_record_inbound_webhook_event,
    webhook_host_allowed as _runtime_webhook_host_allowed,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def collect_json_lists_by_key(value: Any, key: str) -> list[Any]:
    return _runtime_collect_json_lists_by_key(value, key)


def parse_calendar_event_timestamp(value: Any) -> float | None:
    return _runtime_parse_calendar_event_timestamp(_services_module(), value)


def webhook_host_allowed(url: str) -> bool:
    return _runtime_webhook_host_allowed(_services_module(), url)


def record_inbound_webhook_event(
    *,
    payload: Any,
    headers: dict[str, Any] | None = None,
    source: str = "unknown",
    path: str = "/",
) -> int:
    return _runtime_record_inbound_webhook_event(
        _services_module(),
        payload=payload,
        headers=headers,
        source=source,
        path=path,
    )


def record_email_history(recipient: str, subject: str) -> None:
    _runtime_record_email_history(_services_module(), recipient=recipient, subject=subject)


def send_email_sync(*, recipient: str, subject: str, body: str) -> None:
    _runtime_send_email_sync(
        _services_module(),
        recipient=recipient,
        subject=subject,
        body=body,
    )
