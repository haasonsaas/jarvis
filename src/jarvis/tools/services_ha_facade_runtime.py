"""Home Assistant helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_ha_runtime import (
    ha_call_service as _runtime_ha_call_service,
    ha_conversation_speech as _runtime_ha_conversation_speech,
    ha_get_domain_services as _runtime_ha_get_domain_services,
    ha_get_json as _runtime_ha_get_json,
    ha_get_state as _runtime_ha_get_state,
    ha_render_template as _runtime_ha_render_template,
    ha_request_json as _runtime_ha_request_json,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


async def ha_get_state(entity_id: str) -> tuple[dict[str, Any] | None, str | None]:
    return await _runtime_ha_get_state(_services_module(), entity_id)


async def ha_get_domain_services(domain: str) -> tuple[list[str] | None, str | None]:
    return await _runtime_ha_get_domain_services(_services_module(), domain)


async def ha_call_service(
    domain: str,
    service: str,
    service_data: dict[str, Any],
    *,
    return_response: bool = False,
    timeout_sec: float = 10.0,
) -> tuple[list[Any] | None, str | None]:
    return await _runtime_ha_call_service(
        _services_module(),
        domain,
        service,
        service_data,
        return_response=return_response,
        timeout_sec=timeout_sec,
    )


async def ha_get_json(
    path: str,
    *,
    params: dict[str, str] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    return await _runtime_ha_get_json(
        _services_module(),
        path,
        params=params,
        timeout_sec=timeout_sec,
    )


async def ha_request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 10.0,
) -> tuple[Any | None, str | None]:
    return await _runtime_ha_request_json(
        _services_module(),
        method,
        path,
        payload=payload,
        timeout_sec=timeout_sec,
    )


async def ha_render_template(template_text: str, *, timeout_sec: float = 10.0) -> tuple[str | None, str | None]:
    return await _runtime_ha_render_template(_services_module(), template_text, timeout_sec=timeout_sec)


def ha_conversation_speech(payload: dict[str, Any]) -> str:
    return _runtime_ha_conversation_speech(payload)
