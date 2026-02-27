"""Smart-home state action handler."""

from __future__ import annotations

import json
import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def smart_home_state(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _ha_get_state = s._ha_get_state

    start_time = time.monotonic()
    if not _tool_permitted("smart_home_state"):
        record_summary("smart_home_state", "denied", start_time, "policy")
        _audit("smart_home_state", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        _record_service_error("smart_home_state", start_time, "missing_config")
        _audit("smart_home_state", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured."}]}

    entity_id = str(args.get("entity_id", "")).strip().lower()
    if not entity_id:
        _record_service_error("smart_home_state", start_time, "missing_entity")
        _audit("smart_home_state", {"result": "missing_entity"})
        return {"content": [{"type": "text", "text": "Entity id required."}]}
    tool_feedback("start")
    data, error_code = await _ha_get_state(entity_id)
    tool_feedback("done")
    if error_code is not None:
        _record_service_error("smart_home_state", start_time, error_code)
        _audit("smart_home_state", {"result": error_code, "entity_id": entity_id})
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid response from Home Assistant."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}
    payload = data or {}
    record_summary("smart_home_state", "ok", start_time)
    _audit(
        "smart_home_state",
        {
            "result": "ok",
            "entity_id": entity_id,
            "state": payload.get("state", "unknown"),
        },
    )
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "state": payload.get("state", "unknown"),
                        "attributes": payload.get("attributes", {}),
                    }
                ),
            }
        ]
    }
