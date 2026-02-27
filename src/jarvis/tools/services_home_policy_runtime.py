"""Home area-policy runtime helpers for services domains."""

from __future__ import annotations

import re
import time
from typing import Any


def extract_area_from_entity(entity_id: str) -> str:
    text = str(entity_id or "").strip().lower()
    if "." not in text:
        return ""
    _, name = text.split(".", 1)
    cleaned = re.sub(r"[^a-z0-9_]", "_", name)
    parts = [part for part in cleaned.split("_") if part]
    if not parts:
        return ""
    if parts[0] in {"light", "switch", "media", "player", "climate", "lock", "cover"} and len(parts) > 1:
        return parts[1]
    return parts[0]


def home_action_is_loud(*, domain: str, action: str, data: dict[str, Any] | None = None) -> bool:
    domain_text = str(domain or "").strip().lower()
    action_text = str(action or "").strip().lower()
    payload = data if isinstance(data, dict) else {}
    if domain_text == "media_player" and action_text in {"media_play", "play_media", "turn_on", "volume_set"}:
        return True
    if domain_text in {"light", "switch"} and action_text in {"turn_on", "toggle"}:
        brightness = payload.get("brightness")
        if brightness is None:
            return True
        try:
            level = float(brightness)
        except (TypeError, ValueError):
            return True
        return level >= 120.0
    return False


def home_area_policy_violation(
    services_module: Any,
    *,
    domain: str,
    action: str,
    entity_id: str,
    data: dict[str, Any] | None = None,
    now_ts: float | None = None,
) -> tuple[bool, str]:
    s = services_module
    area = extract_area_from_entity(entity_id)
    if not area:
        return False, ""
    policy = s._home_area_policies.get(area)
    if not isinstance(policy, dict):
        return False, ""
    blocked_pairs = {
        item
        for item in s._as_str_list(policy.get("blocked_actions"), lower=True)
        if ":" in item
    }
    pair = f"{str(domain).strip().lower()}:{str(action).strip().lower()}"
    if pair in blocked_pairs:
        return True, f"Area policy for '{area}' blocks action {pair}."
    quiet_start = str(policy.get("quiet_hours_start", "")).strip()
    quiet_end = str(policy.get("quiet_hours_end", "")).strip()
    if quiet_start and quiet_end:
        start = s._hhmm_to_minutes(quiet_start)
        end = s._hhmm_to_minutes(quiet_end)
        if start is not None and end is not None and start != end:
            local = time.localtime(time.time() if now_ts is None else float(now_ts))
            minute = (local.tm_hour * 60) + local.tm_min
            in_quiet = (start <= minute < end) if start < end else (minute >= start or minute < end)
            if in_quiet and home_action_is_loud(domain=domain, action=action, data=data):
                return True, f"Area policy quiet hours are active for '{area}' and loud actions are blocked."
    return False, ""
