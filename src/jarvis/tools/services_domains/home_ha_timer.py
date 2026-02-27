"""Home Assistant timer handler."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.home_ha_timer_mutate_action import home_assistant_timer_mutate
from jarvis.tools.services_domains.home_ha_timer_preflight import home_assistant_timer_prepare
from jarvis.tools.services_domains.home_ha_timer_state_action import home_assistant_timer_state


async def home_assistant_timer(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    context, early_response = home_assistant_timer_prepare(args, start_time=start_time)
    if early_response is not None:
        return early_response
    if context is None:
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}

    action = str(context.get("action", "")).strip().lower()
    if action == "state":
        return await home_assistant_timer_state(context, start_time=start_time)
    return await home_assistant_timer_mutate(context, start_time=start_time)
