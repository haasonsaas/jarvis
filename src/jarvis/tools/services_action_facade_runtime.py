"""Action-history helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_action_runtime import (
    action_key as _runtime_action_key,
    cooldown_active as _runtime_cooldown_active,
    prune_action_history as _runtime_prune_action_history,
    retry_backoff_delay as _runtime_retry_backoff_delay,
    touch_action as _runtime_touch_action,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def action_key(domain: str, action: str, entity_id: str) -> str:
    return _runtime_action_key(domain, action, entity_id)


def prune_action_history(now: float | None = None) -> None:
    _runtime_prune_action_history(_services_module(), now=now)


def cooldown_active(domain: str, action: str, entity_id: str) -> bool:
    return _runtime_cooldown_active(_services_module(), domain, action, entity_id)


def touch_action(domain: str, action: str, entity_id: str) -> None:
    _runtime_touch_action(_services_module(), domain, action, entity_id)


def retry_backoff_delay(
    attempt_index: int,
    *,
    base_delay_sec: float,
    max_delay_sec: float,
    jitter_ratio: float,
    jitter_sample: float | None = None,
) -> float:
    return _runtime_retry_backoff_delay(
        _services_module(),
        attempt_index,
        base_delay_sec=base_delay_sec,
        max_delay_sec=max_delay_sec,
        jitter_ratio=jitter_ratio,
        jitter_sample=jitter_sample,
    )
