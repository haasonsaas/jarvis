"""Home Assistant conversation handler."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.home_ha_conversation_execute import home_ha_conversation_execute
from jarvis.tools.services_domains.home_ha_conversation_preflight import home_ha_conversation_preflight


def _services():
    from jarvis.tools import services as s

    return s


async def home_assistant_conversation(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    context, early_response = await home_ha_conversation_preflight(args, start_time=start_time)
    if early_response is not None:
        return early_response
    if context is None:
        _record_service_error("home_assistant_conversation", start_time, "unexpected")
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant conversation error."}]}

    return await home_ha_conversation_execute(context, start_time=start_time)
