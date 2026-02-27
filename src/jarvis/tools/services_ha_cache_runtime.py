"""Home Assistant cache/header helper extraction for `jarvis.tools.services`."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.service_policy import HA_MUTATING_ALLOWED_ACTIONS


def ha_headers(services: Any) -> dict[str, str]:
    assert services._config is not None
    return {"Authorization": f"Bearer {services._config.hass_token}"}


def ha_cached_state(services: Any, entity_id: str) -> dict[str, Any] | None:
    item = services._ha_state_cache.get(entity_id)
    if item is None:
        return None
    expires_at, payload = item
    if expires_at < time.monotonic():
        services._ha_state_cache.pop(entity_id, None)
        return None
    return payload


def ha_invalidate_state(services: Any, entity_id: str) -> None:
    services._ha_state_cache.pop(entity_id, None)


def ha_action_allowed(domain: str, action: str) -> bool:
    allowed = HA_MUTATING_ALLOWED_ACTIONS.get(domain)
    if allowed is None:
        return False
    return action in allowed
