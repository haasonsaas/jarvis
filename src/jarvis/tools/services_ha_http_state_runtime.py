"""Home Assistant state and service-discovery HTTP helpers."""

from __future__ import annotations

import asyncio
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
