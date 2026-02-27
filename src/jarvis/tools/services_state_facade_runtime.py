"""Runtime state/helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.config import Config
from jarvis.memory import MemoryStore
from jarvis.tools.services_runtime_state import (
    append_quality_report as _runtime_append_quality_report,
    bind_runtime_state as _runtime_bind_runtime_state,
    expansion_state_payload as _runtime_expansion_state_payload,
    json_safe_clone as _runtime_json_safe_clone,
    load_expansion_state as _runtime_load_expansion_state,
    persist_expansion_state as _runtime_persist_expansion_state,
    quality_reports_snapshot as _runtime_quality_reports_snapshot,
    replace_state_dict as _runtime_replace_state_dict,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def bind_runtime_state(config: Config, memory_store: MemoryStore | None = None) -> None:
    _runtime_bind_runtime_state(_services_module(), config, memory_store)


def quality_reports_snapshot(*, limit: int = 10) -> list[dict[str, Any]]:
    return _runtime_quality_reports_snapshot(_services_module(), limit=limit)


def append_quality_report(report: dict[str, Any]) -> None:
    _runtime_append_quality_report(_services_module(), report)


def json_safe_clone(value: Any) -> Any:
    return _runtime_json_safe_clone(value)


def replace_state_dict(target: dict[str, Any], source: Any) -> None:
    _runtime_replace_state_dict(_services_module(), target, source)


def expansion_state_payload() -> dict[str, Any]:
    return _runtime_expansion_state_payload(_services_module())


def persist_expansion_state() -> None:
    _runtime_persist_expansion_state(_services_module())


def load_expansion_state() -> None:
    _runtime_load_expansion_state(_services_module())
