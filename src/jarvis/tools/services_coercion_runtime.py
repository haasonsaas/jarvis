"""Coercion/normalization runtime helpers for services domains."""

from __future__ import annotations

import math
from typing import Any


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return default
        return bool(value)
    return default


def as_int(
    value: Any,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        parsed = default
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            parsed = default
        else:
            parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if text and (text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit())):
            try:
                parsed = int(text)
            except ValueError:
                parsed = default
        else:
            parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def as_exact_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit()):
            try:
                return int(text)
            except ValueError:
                return None
        return None
    return None


def as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        parsed = default
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
    if not math.isfinite(parsed):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def effective_act_timeout(
    services_module: Any,
    total_sec: Any,
    *,
    minimum: float = 0.1,
    maximum: float = 120.0,
) -> float:
    s = services_module
    requested = as_float(total_sec, s._turn_timeout_act_sec, minimum=minimum, maximum=maximum)
    budget = as_float(s._turn_timeout_act_sec, requested, minimum=minimum, maximum=maximum)
    return min(requested, budget)


def as_str_list(value: Any, *, lower: bool = False, allow_none: bool = False) -> list[str] | None:
    if value is None:
        return None if allow_none else []
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if lower:
            cleaned = [item.lower() for item in cleaned]
        if cleaned:
            return cleaned
        return None if allow_none else []
    if isinstance(value, tuple):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if lower:
            cleaned = [item.lower() for item in cleaned]
        if cleaned:
            return cleaned
        return None if allow_none else []
    text = str(value).strip()
    if not text:
        return None if allow_none else []
    if lower:
        text = text.lower()
    return [text]
