"""Compatibility wrapper for Home Assistant HTTP/runtime helpers."""

from __future__ import annotations

from jarvis.tools.services_ha_http_runtime import (
    ha_call_service,
    ha_get_domain_services,
    ha_get_json,
    ha_get_state,
    ha_render_template,
    ha_request_json,
)
from jarvis.tools.services_ha_response_runtime import ha_conversation_speech

__all__ = [
    "ha_call_service",
    "ha_conversation_speech",
    "ha_get_domain_services",
    "ha_get_json",
    "ha_get_state",
    "ha_render_template",
    "ha_request_json",
]
