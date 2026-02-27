"""Outbound webhook trigger handler."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.integrations_webhook_trigger_execute import webhook_trigger_execute
from jarvis.tools.services_domains.integrations_webhook_trigger_preflight import webhook_trigger_prepare


def _services():
    from jarvis.tools import services as s

    return s


async def webhook_trigger(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    time = s.time
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    context, early_response = webhook_trigger_prepare(args, start_time=start_time)
    if early_response is not None:
        return early_response
    if context is None:
        _record_service_error("webhook_trigger", start_time, "unexpected")
        return {"content": [{"type": "text", "text": "Unexpected webhook trigger error."}]}

    return await webhook_trigger_execute(context, start_time=start_time)
