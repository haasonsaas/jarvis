"""Smart-home mutation handlers."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.home_mutation_execute import home_mutation_apply
from jarvis.tools.services_domains.home_mutation_preflight import home_mutation_prepare


def _services():
    from jarvis.tools import services as s

    return s


async def smart_home(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("smart_home"):
        record_summary("smart_home", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    if not _config or not _config.has_home_assistant:
        _record_service_error("smart_home", start_time, "missing_config")
        return {
            "content": [
                {"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}
            ]
        }

    context, early_response = await home_mutation_prepare(args, start_time=start_time)
    if early_response is not None:
        return early_response
    if context is None:
        _record_service_error("smart_home", start_time, "unexpected")
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}

    return await home_mutation_apply(context, start_time=start_time)
