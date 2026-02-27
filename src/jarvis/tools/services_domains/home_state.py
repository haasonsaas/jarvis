"""Home Assistant state and capability handlers."""

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


async def home_assistant_capabilities(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _audit = s._audit
    _record_service_error = s._record_service_error
    _config = s._config
    _as_bool = s._as_bool
    _ha_get_state = s._ha_get_state
    _ha_get_domain_services = s._ha_get_domain_services

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_capabilities"):
        record_summary("home_assistant_capabilities", "denied", start_time, "policy")
        _audit("home_assistant_capabilities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_capabilities", start_time, "missing_config")
        _audit("home_assistant_capabilities", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    entity_id = str(args.get("entity_id", "")).strip().lower()
    if not entity_id:
        _record_service_error("home_assistant_capabilities", start_time, "missing_entity")
        _audit("home_assistant_capabilities", {"result": "missing_entity"})
        return {"content": [{"type": "text", "text": "Entity id required."}]}
    include_services = _as_bool(args.get("include_services"), default=True)

    state_payload, state_error = await _ha_get_state(entity_id)
    if state_error is not None:
        _record_service_error("home_assistant_capabilities", start_time, state_error)
        _audit("home_assistant_capabilities", {"result": state_error, "entity_id": entity_id})
        if state_error == "not_found":
            return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if state_error == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if state_error == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid response from Home Assistant."}]}
        if state_error == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        if state_error == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        if state_error == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if state_error == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}

    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    services_for_domain: list[str] = []
    if include_services and domain:
        service_names, service_error = await _ha_get_domain_services(domain)
        if service_error is not None:
            _record_service_error("home_assistant_capabilities", start_time, service_error)
            _audit(
                "home_assistant_capabilities",
                {
                    "result": service_error,
                    "entity_id": entity_id,
                    "domain": domain,
                    "phase": "service_catalog",
                },
            )
            if service_error == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed while reading services."}]}
            if service_error == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant service catalog response."}]}
            if service_error == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant service catalog request timed out."}]}
            if service_error == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant service catalog request was cancelled."}]}
            if service_error == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if service_error == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant service catalog endpoint."}]}
            return {"content": [{"type": "text", "text": "Unable to fetch Home Assistant service catalog."}]}
        services_for_domain = service_names or []

    payload = state_payload or {}
    result = {
        "entity_id": entity_id,
        "domain": domain,
        "state": payload.get("state", "unknown"),
        "attributes": payload.get("attributes", {}),
        "available_services": services_for_domain,
    }
    record_summary("home_assistant_capabilities", "ok", start_time)
    _audit(
        "home_assistant_capabilities",
        {
            "result": "ok",
            "entity_id": entity_id,
            "domain": domain,
            "include_services": include_services,
            "service_count": len(services_for_domain),
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


