"""Integrations domain runtime helpers."""

from __future__ import annotations

from typing import Any, Callable


def parse_calendar_window(
    args: dict[str, Any],
    *,
    now_ts: float,
    parse_due_timestamp: Callable[[Any], float | None],
    as_float: Callable[[Any, float], float],
    default_window_hours: float,
    max_window_hours: float,
) -> tuple[float | None, float | None]:
    start_raw = str(args.get("start", "")).strip()
    end_raw = str(args.get("end", "")).strip()
    start_ts = now_ts
    if start_raw:
        parsed_start = parse_due_timestamp(start_raw)
        if parsed_start is None:
            return None, None
        start_ts = parsed_start
    if end_raw:
        end_ts = parse_due_timestamp(end_raw)
        if end_ts is None:
            return None, None
    else:
        window_hours = as_float(
            args.get("window_hours", default_window_hours),
            default_window_hours,
        )
        window_hours = max(0.1, min(max_window_hours, float(window_hours)))
        end_ts = start_ts + (window_hours * 3600.0)
    if end_ts <= start_ts:
        return None, None
    return start_ts, end_ts
