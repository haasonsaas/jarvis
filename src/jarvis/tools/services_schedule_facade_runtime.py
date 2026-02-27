"""Schedule/timer/reminder helper facade decoupled from services.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from jarvis.tools.services_schedule_runtime import (
    allocate_reminder_id as _runtime_allocate_reminder_id,
    allocate_timer_id as _runtime_allocate_timer_id,
    duration_seconds as _runtime_duration_seconds,
    format_duration as _runtime_format_duration,
    load_reminders_from_store as _runtime_load_reminders_from_store,
    load_timers_from_store as _runtime_load_timers_from_store,
    local_timezone as _runtime_local_timezone,
    parse_datetime_text as _runtime_parse_datetime_text,
    parse_due_timestamp as _runtime_parse_due_timestamp,
    prune_timers as _runtime_prune_timers,
    reminder_status as _runtime_reminder_status,
    timer_status as _runtime_timer_status,
    timestamp_to_iso_utc as _runtime_timestamp_to_iso_utc,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def duration_seconds(value: Any) -> float | None:
    return _runtime_duration_seconds(_services_module(), value)


def local_timezone():
    return _runtime_local_timezone()


def parse_datetime_text(value: str) -> datetime | None:
    return _runtime_parse_datetime_text(value)


def parse_due_timestamp(value: Any, *, now_ts: float | None = None) -> float | None:
    return _runtime_parse_due_timestamp(_services_module(), value, now_ts=now_ts)


def timestamp_to_iso_utc(ts: float) -> str:
    return _runtime_timestamp_to_iso_utc(ts)


def format_duration(seconds: float) -> str:
    return _runtime_format_duration(seconds)


def allocate_timer_id() -> int:
    return _runtime_allocate_timer_id(_services_module())


def allocate_reminder_id() -> int:
    return _runtime_allocate_reminder_id(_services_module())


def prune_timers(*, now_mono: float | None = None) -> None:
    _runtime_prune_timers(_services_module(), now_mono=now_mono)


def timer_status() -> dict[str, Any]:
    return _runtime_timer_status(_services_module())


def load_timers_from_store() -> None:
    _runtime_load_timers_from_store(_services_module())


def reminder_status() -> dict[str, Any]:
    return _runtime_reminder_status(_services_module())


def load_reminders_from_store() -> None:
    _runtime_load_reminders_from_store(_services_module())
