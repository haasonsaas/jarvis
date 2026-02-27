"""Action cooldown and retry helper runtime helpers for services domains."""

from __future__ import annotations

import random
import time
from typing import Any


def retry_backoff_delay(
    services_module: Any,
    attempt_index: int,
    *,
    base_delay_sec: float,
    max_delay_sec: float,
    jitter_ratio: float,
    jitter_sample: float | None = None,
) -> float:
    step = max(0, int(attempt_index))
    base_delay = min(max_delay_sec, base_delay_sec * (2 ** step))
    sample = random.random() if jitter_sample is None else float(jitter_sample)
    sample = min(1.0, max(0.0, sample))
    jitter = base_delay * jitter_ratio * ((sample * 2.0) - 1.0)
    return max(0.0, base_delay + jitter)


def action_key(domain: str, action: str, entity_id: str) -> str:
    return f"{domain}:{action}:{entity_id}"


def prune_action_history(services_module: Any, now: float | None = None) -> None:
    s = services_module
    if not s._action_last_seen:
        return
    current = time.monotonic() if now is None else now
    cutoff = current - s.ACTION_HISTORY_RETENTION_SEC
    stale_keys = [key for key, ts in s._action_last_seen.items() if ts < cutoff]
    for key in stale_keys:
        s._action_last_seen.pop(key, None)
    if len(s._action_last_seen) <= s.ACTION_HISTORY_MAX_ENTRIES:
        return
    over = len(s._action_last_seen) - s.ACTION_HISTORY_MAX_ENTRIES
    oldest = sorted(s._action_last_seen.items(), key=lambda item: item[1])[:over]
    for key, _ in oldest:
        s._action_last_seen.pop(key, None)


def cooldown_active(services_module: Any, domain: str, action: str, entity_id: str) -> bool:
    s = services_module
    now = time.monotonic()
    prune_action_history(s, now)
    key = action_key(domain, action, entity_id)
    last = s._action_last_seen.get(key)
    if last is None:
        return False
    return (now - last) < s.ACTION_COOLDOWN_SEC


def touch_action(services_module: Any, domain: str, action: str, entity_id: str) -> None:
    s = services_module
    now = time.monotonic()
    s._action_last_seen[action_key(domain, action, entity_id)] = now
    prune_action_history(s, now)
