"""Post-action effect verification helpers for home actions."""

from __future__ import annotations

import asyncio
import time
from typing import Any


_EXPECTED_STATE_BY_ACTION: dict[str, dict[str, str]] = {
    "light": {
        "turn_on": "on",
        "turn_off": "off",
    },
    "switch": {
        "turn_on": "on",
        "turn_off": "off",
    },
    "fan": {
        "turn_on": "on",
        "turn_off": "off",
    },
    "lock": {
        "lock": "locked",
        "unlock": "unlocked",
    },
    "cover": {
        "open_cover": "open",
        "close_cover": "closed",
    },
    "media_player": {
        "media_play": "playing",
        "media_pause": "paused",
        "media_stop": "idle",
    },
}


def expected_state_for_action(*, domain: str, action: str) -> str:
    domain_key = str(domain or "").strip().lower()
    action_key = str(action or "").strip().lower()
    if not domain_key or not action_key:
        return ""
    mapped = _EXPECTED_STATE_BY_ACTION.get(domain_key, {})
    if not mapped:
        return ""
    return str(mapped.get(action_key, "")).strip().lower()


async def verify_home_action_effect(
    services_module: Any,
    *,
    domain: str,
    action: str,
    entity_id: str,
    enabled_domains: list[str],
    max_attempts: int = 2,
) -> dict[str, Any]:
    s = services_module
    domain_key = str(domain or "").strip().lower()
    action_key = str(action or "").strip().lower()
    entity = str(entity_id or "").strip().lower()
    if not domain_key or not action_key or not entity:
        return {
            "applied": False,
            "verified": False,
            "reason": "missing_fields",
        }

    domains = {
        str(item).strip().lower()
        for item in enabled_domains
        if str(item).strip()
    }
    if domain_key not in domains:
        return {
            "applied": False,
            "verified": False,
            "reason": "domain_not_enabled",
            "domain": domain_key,
        }

    expected_state = expected_state_for_action(domain=domain_key, action=action_key)
    if not expected_state:
        return {
            "applied": False,
            "verified": False,
            "reason": "unsupported_action",
            "domain": domain_key,
            "action": action_key,
        }

    now = time.time()
    attempts = max(1, min(5, int(max_attempts)))
    observed_state = ""
    error_code = ""
    for attempt in range(attempts):
        payload, err = await s._ha_get_state(entity)
        error_code = str(err or "").strip().lower()
        if isinstance(payload, dict):
            observed_state = str(payload.get("state", "")).strip().lower()
        if observed_state:
            break
        if error_code:
            break
        if attempt + 1 < attempts:
            await asyncio.sleep(0.2)

    if error_code:
        return {
            "applied": True,
            "verified": False,
            "reason": "state_lookup_error",
            "domain": domain_key,
            "action": action_key,
            "entity_id": entity,
            "expected_state": expected_state,
            "observed_state": observed_state,
            "error_code": error_code,
            "checked_at": now,
        }

    verified = observed_state == expected_state
    reason = "verified" if verified else "state_mismatch"
    return {
        "applied": True,
        "verified": bool(verified),
        "reason": reason,
        "domain": domain_key,
        "action": action_key,
        "entity_id": entity,
        "expected_state": expected_state,
        "observed_state": observed_state,
        "checked_at": now,
    }
