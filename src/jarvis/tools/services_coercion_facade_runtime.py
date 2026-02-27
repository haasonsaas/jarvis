"""Coercion helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_coercion_runtime import (
    as_bool as _runtime_as_bool,
    as_exact_int as _runtime_as_exact_int,
    as_float as _runtime_as_float,
    as_int as _runtime_as_int,
    as_str_list as _runtime_as_str_list,
    effective_act_timeout as _runtime_effective_act_timeout,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def as_bool(value: Any, default: bool = False) -> bool:
    return _runtime_as_bool(value, default=default)


def as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    return _runtime_as_int(value, default, minimum=minimum, maximum=maximum)


def as_exact_int(value: Any) -> int | None:
    return _runtime_as_exact_int(value)


def as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    return _runtime_as_float(value, default, minimum=minimum, maximum=maximum)


def effective_act_timeout(total_sec: Any, *, minimum: float = 0.1, maximum: float = 120.0) -> float:
    return _runtime_effective_act_timeout(_services_module(), total_sec, minimum=minimum, maximum=maximum)


def as_str_list(value: Any, *, lower: bool = False, allow_none: bool = False) -> list[str] | None:
    return _runtime_as_str_list(value, lower=lower, allow_none=allow_none)
