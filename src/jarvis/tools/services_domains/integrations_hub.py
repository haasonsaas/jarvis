"""Integration domain service handlers extracted from services.py."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_domains.integrations_hub_calendar_notes import (
    integration_hub_calendar_delete,
    integration_hub_calendar_upsert,
    integration_hub_notes_capture,
)
from jarvis.tools.services_domains.integrations_hub_messaging import (
    integration_hub_commute_brief,
    integration_hub_messaging_flow,
    integration_hub_research_workflow,
    integration_hub_shopping_orchestrate,
)
from jarvis.tools.services_domains.integrations_hub_release_channels import (
    integration_hub_release_channel_check,
    integration_hub_release_channel_get,
    integration_hub_release_channel_set,
)


def _services():
    from jarvis.tools import services as s

    return s


async def integration_hub(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("integration_hub"):
        record_summary("integration_hub", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "calendar_upsert":
        return await integration_hub_calendar_upsert(args, start_time=start_time)
    if action == "calendar_delete":
        return await integration_hub_calendar_delete(args, start_time=start_time)
    if action == "notes_capture":
        return await integration_hub_notes_capture(args, start_time=start_time)
    if action == "messaging_flow":
        return await integration_hub_messaging_flow(args, start_time=start_time)
    if action == "commute_brief":
        return await integration_hub_commute_brief(args, start_time=start_time)
    if action == "shopping_orchestrate":
        return await integration_hub_shopping_orchestrate(args, start_time=start_time)
    if action == "research_workflow":
        return await integration_hub_research_workflow(args, start_time=start_time)
    if action == "release_channel_get":
        return await integration_hub_release_channel_get(args, start_time=start_time)
    if action == "release_channel_set":
        return await integration_hub_release_channel_set(args, start_time=start_time)
    if action == "release_channel_check":
        return await integration_hub_release_channel_check(args, start_time=start_time)

    _record_service_error("integration_hub", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown integration_hub action."}]}
