"""Home Assistant media-control handler."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.home_media_control_execute import home_media_control_execute
from jarvis.tools.services_domains.home_media_control_preflight import home_media_control_prepare


async def media_control(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    context, early_response = home_media_control_prepare(args, start_time=start_time)
    if early_response is not None:
        return early_response
    if context is None:
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant media control error."}]}
    return await home_media_control_execute(context, start_time=start_time)
