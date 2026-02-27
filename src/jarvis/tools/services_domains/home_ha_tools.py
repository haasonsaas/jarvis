"""Compatibility exports for Home Assistant conversation/todo/timer/area/media handlers."""

from __future__ import annotations

from jarvis.tools.services_domains.home_ha_area_media import (
    home_assistant_area_entities,
    media_control,
)
from jarvis.tools.services_domains.home_ha_conversation import home_assistant_conversation
from jarvis.tools.services_domains.home_ha_timer import home_assistant_timer
from jarvis.tools.services_domains.home_ha_todo import home_assistant_todo

__all__ = [
    "home_assistant_conversation",
    "home_assistant_todo",
    "home_assistant_timer",
    "home_assistant_area_entities",
    "media_control",
]
