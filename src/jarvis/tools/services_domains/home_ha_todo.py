"""Home Assistant to-do handler."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.home_ha_todo_list_action import home_assistant_todo_list
from jarvis.tools.services_domains.home_ha_todo_mutate_action import home_assistant_todo_mutate
from jarvis.tools.services_domains.home_ha_todo_preflight import home_assistant_todo_prepare


async def home_assistant_todo(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    context, early_response = home_assistant_todo_prepare(args, start_time=start_time)
    if early_response is not None:
        return early_response
    if context is None:
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}

    action = str(context.get("action", "")).strip().lower()
    if action == "list":
        return await home_assistant_todo_list(context, start_time=start_time)
    return await home_assistant_todo_mutate(context, start_time=start_time)
