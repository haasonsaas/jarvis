"""Home Assistant area-entities handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_assistant_area_entities(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _ha_render_template = s._ha_render_template
    _ha_get_state = s._ha_get_state

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_area_entities"):
        record_summary("home_assistant_area_entities", "denied", start_time, "policy")
        _audit("home_assistant_area_entities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_area_entities", start_time, "missing_config")
        _audit("home_assistant_area_entities", {"result": "missing_config"})
        return {
            "content": [
                {"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}
            ]
        }

    area = str(args.get("area", "")).strip()
    if not area:
        _record_service_error("home_assistant_area_entities", start_time, "missing_fields")
        _audit("home_assistant_area_entities", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "area is required."}]}
    domain_filter = str(args.get("domain", "")).strip().lower()
    include_states = _as_bool(args.get("include_states"), default=False)

    template = f"{{{{ area_entities({json.dumps(area)}) | join('\\n') }}}}"
    rendered, error_code = await _ha_render_template(template)
    if error_code is not None:
        _record_service_error("home_assistant_area_entities", start_time, error_code)
        _audit("home_assistant_area_entities", {"result": error_code, "area": area})
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Home Assistant template endpoint not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup was cancelled."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant area lookup endpoint."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant area lookup error."}]}

    raw_entities = [line.strip().lower() for line in (rendered or "").splitlines() if line.strip()]
    entities = sorted(set(raw_entities))
    if domain_filter:
        entities = [entity for entity in entities if entity.startswith(f"{domain_filter}.")]
    if not entities:
        record_summary("home_assistant_area_entities", "empty", start_time)
        _audit(
            "home_assistant_area_entities",
            {"result": "empty", "area": area, "domain": domain_filter},
        )
        return {"content": [{"type": "text", "text": "No entities found for that area filter."}]}

    payload: dict[str, Any] = {"area": area, "domain": domain_filter or None, "entities": entities}
    if include_states:
        states: list[dict[str, Any]] = []
        for entity_id in entities[:100]:
            entity_state, state_error = await _ha_get_state(entity_id)
            if state_error is not None:
                continue
            state_payload = entity_state or {}
            attributes = state_payload.get("attributes")
            friendly_name = ""
            if isinstance(attributes, dict):
                friendly_name = str(attributes.get("friendly_name", "")).strip()
            states.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "state": state_payload.get("state", "unknown"),
                }
            )
        payload["states"] = states
    record_summary("home_assistant_area_entities", "ok", start_time)
    _audit(
        "home_assistant_area_entities",
        {
            "result": "ok",
            "area": area,
            "domain": domain_filter,
            "count": len(entities),
            "include_states": include_states,
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}
