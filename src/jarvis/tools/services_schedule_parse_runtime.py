"""Scheduling/datetime parse helpers for services domains."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

def duration_seconds(services_module: Any, value: Any) -> float | None:
    s = services_module
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0.0:
            return None
        return min(seconds, s.TIMER_MAX_SECONDS)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    try:
        parsed = float(text)
        if math.isfinite(parsed) and parsed > 0.0:
            return min(parsed, s.TIMER_MAX_SECONDS)
    except ValueError:
        pass
    total = 0.0
    cursor = 0
    for match in s._DURATION_SEGMENT_RE.finditer(text):
        if match.start() != cursor and text[cursor : match.start()].strip():
            return None
        value_part = float(match.group("value"))
        unit = match.group("unit").lower()
        if unit.startswith("h"):
            total += value_part * 3600.0
        elif unit.startswith("m"):
            total += value_part * 60.0
        else:
            total += value_part
        cursor = match.end()
    if cursor != len(text) and text[cursor:].strip():
        return None
    if total <= 0.0:
        return None
    return min(total, s.TIMER_MAX_SECONDS)


def local_timezone() -> Any:
    tz = datetime.now().astimezone().tzinfo
    return tz if tz is not None else timezone.utc


def parse_datetime_text(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone())
    return parsed


def parse_due_timestamp(services_module: Any, value: Any, *, now_ts: float | None = None) -> float | None:
    s = services_module
    now = s.time.time() if now_ts is None else float(now_ts)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidate = float(value)
        if not math.isfinite(candidate) or candidate <= 0.0:
            return None
        if candidate >= 1_000_000_000.0:
            return candidate
        return now + min(candidate, s.TIMER_MAX_SECONDS)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    numeric = None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and math.isfinite(numeric) and numeric > 0.0:
        if numeric >= 1_000_000_000.0:
            return numeric
        return now + min(numeric, s.TIMER_MAX_SECONDS)
    if lowered.startswith("in "):
        relative = duration_seconds(s, lowered[3:])
        if relative is not None:
            return now + relative
    relative = duration_seconds(s, text)
    if relative is not None:
        return now + relative
    parsed = parse_datetime_text(text)
    if parsed is None:
        return None
    return parsed.timestamp()


def timestamp_to_iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def format_duration(seconds: float) -> str:
    remaining = max(0, int(round(seconds)))
    hours, rem = divmod(remaining, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
