"""Home Assistant HTTP/runtime helpers for services domains."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp


async def ha_get_state(services_module: Any, entity_id: str) -> tuple[dict[str, Any] | None, str | None]:
    s = services_module
    if s._integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    cached = s._ha_cached_state(entity_id)
    if cached is not None:
        return cached, None
    assert s._config is not None
    url = f"{s._config.hass_url}/api/states/{entity_id}"
    timeout = aiohttp.ClientTimeout(total=s._effective_act_timeout(5.0))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=s._ha_headers()) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, dict):
                        return None, "invalid_json"
                    s._ha_state_cache[entity_id] = (s.time.monotonic() + s.HA_STATE_CACHE_TTL_SEC, data)
                    s._integration_record_success("home_assistant")
                    return data, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def ha_get_domain_services(services_module: Any, domain: str) -> tuple[list[str] | None, str | None]:
    s = services_module
    if s._integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert s._config is not None
    url = f"{s._config.hass_url}/api/services"
    timeout = aiohttp.ClientTimeout(total=s._effective_act_timeout(5.0))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=s._ha_headers()) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, list):
                        return None, "invalid_json"
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("domain", "")).strip().lower() != domain:
                            continue
                        raw_services = item.get("services")
                        if not isinstance(raw_services, dict):
                            return [], None
                        names = sorted(
                            {
                                str(name).strip()
                                for name in raw_services.keys()
                                if str(name).strip()
                            }
                        )
                        s._integration_record_success("home_assistant")
                        return names, None
                    s._integration_record_success("home_assistant")
                    return [], None
                if resp.status == 401:
                    return None, "auth"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def ha_call_service(
    services_module: Any,
    domain: str,
    service: str,
    service_data: dict[str, Any],
    *,
    return_response: bool = False,
    timeout_sec: float = 10.0,
) -> tuple[list[Any] | None, str | None]:
    s = services_module
    if s._integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert s._config is not None
    suffix = "?return_response" if return_response else ""
    url = f"{s._config.hass_url}/api/services/{domain}/{service}{suffix}"
    timeout = aiohttp.ClientTimeout(total=s._effective_act_timeout(timeout_sec))
    headers = {**s._ha_headers(), "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=service_data) as resp:
                if resp.status in {200, 201}:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, list):
                        return None, "invalid_json"
                    s._integration_record_success("home_assistant")
                    return data, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def ha_get_json(
    services_module: Any,
    path: str,
    *,
    params: dict[str, str] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    s = services_module
    if s._integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert s._config is not None
    url = f"{s._config.hass_url}{path}"
    timeout = aiohttp.ClientTimeout(total=s._effective_act_timeout(timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=s._ha_headers(), params=params or None) as resp:
                if resp.status == 200:
                    try:
                        payload = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    s._integration_record_success("home_assistant")
                    return payload, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def ha_request_json(
    services_module: Any,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    s = services_module
    if s._integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert s._config is not None
    normalized_method = str(method).strip().upper() or "GET"
    url = f"{s._config.hass_url}{path}"
    timeout = aiohttp.ClientTimeout(total=s._effective_act_timeout(timeout_sec))
    headers = s._ha_headers()
    if payload is not None:
        headers = {**headers, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                normalized_method,
                url,
                headers=headers,
                json=payload if payload is not None else None,
            ) as resp:
                if resp.status in {200, 201, 202, 204}:
                    if resp.status == 204:
                        s._integration_record_success("home_assistant")
                        return {}, None
                    text = await resp.text()
                    if not text.strip():
                        s._integration_record_success("home_assistant")
                        return {}, None
                    try:
                        body = json.loads(text)
                    except Exception:
                        return None, "invalid_json"
                    s._integration_record_success("home_assistant")
                    return body, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


async def ha_render_template(
    services_module: Any,
    template_text: str,
    *,
    timeout_sec: float = 10.0,
) -> tuple[str | None, str | None]:
    s = services_module
    if s._integration_circuit_open("home_assistant")[0]:
        return None, "circuit_open"
    assert s._config is not None
    url = f"{s._config.hass_url}/api/template"
    timeout = aiohttp.ClientTimeout(total=s._effective_act_timeout(timeout_sec))
    headers = {**s._ha_headers(), "Content-Type": "text/plain"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, data=template_text) as resp:
                if resp.status == 200:
                    try:
                        payload = await resp.text()
                    except Exception:
                        return None, "invalid_json"
                    s._integration_record_success("home_assistant")
                    return payload, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"
