"""Memory/planning helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_memory_runtime import (
    expansion_payload_response as _runtime_expansion_payload_response,
    infer_memory_scope as _runtime_infer_memory_scope,
    json_payload_response as _runtime_json_payload_response,
    memory_confidence_label as _runtime_memory_confidence_label,
    memory_confidence_score as _runtime_memory_confidence_score,
    memory_entry_scope as _runtime_memory_entry_scope,
    memory_policy_scopes_for_query as _runtime_memory_policy_scopes_for_query,
    memory_requested_scopes as _runtime_memory_requested_scopes,
    memory_scope_for_add as _runtime_memory_scope_for_add,
    memory_scope_from_tags as _runtime_memory_scope_from_tags,
    memory_scope_tag as _runtime_memory_scope_tag,
    memory_scope_tags as _runtime_memory_scope_tags,
    memory_source_trail as _runtime_memory_source_trail,
    memory_visible_tags as _runtime_memory_visible_tags,
    normalize_memory_scope as _runtime_normalize_memory_scope,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def normalize_memory_scope(value: Any) -> str | None:
    return _runtime_normalize_memory_scope(_services_module(), value)


def memory_scope_tag(scope: str) -> str:
    return _runtime_memory_scope_tag(_services_module(), scope)


def memory_scope_from_tags(tags: list[str] | None) -> str | None:
    return _runtime_memory_scope_from_tags(_services_module(), tags)


def infer_memory_scope(*, kind: str, source: str) -> str:
    return _runtime_infer_memory_scope(kind=kind, source=source)


def memory_scope_for_add(*, kind: str, source: str, tags: list[str], requested_scope: Any) -> str:
    return _runtime_memory_scope_for_add(
        _services_module(),
        kind=kind,
        source=source,
        tags=tags,
        requested_scope=requested_scope,
    )


def memory_scope_tags(tags: list[str], scope: str) -> list[str]:
    return _runtime_memory_scope_tags(_services_module(), tags, scope)


def memory_visible_tags(tags: list[str]) -> list[str]:
    return _runtime_memory_visible_tags(_services_module(), tags)


def memory_entry_scope(entry: Any) -> str:
    return _runtime_memory_entry_scope(_services_module(), entry)


def memory_policy_scopes_for_query(query: str) -> list[str]:
    return _runtime_memory_policy_scopes_for_query(_services_module(), query)


def memory_requested_scopes(scopes_value: Any, *, query: str = "") -> list[str]:
    return _runtime_memory_requested_scopes(_services_module(), scopes_value, query=query)


def memory_confidence_score(entry: Any, *, now_ts: float | None = None) -> float:
    return _runtime_memory_confidence_score(_services_module(), entry, now_ts=now_ts)


def memory_confidence_label(score: float) -> str:
    return _runtime_memory_confidence_label(score)


def memory_source_trail(entry: Any) -> str:
    return _runtime_memory_source_trail(entry)


def json_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _runtime_json_payload_response(payload)


def expansion_payload_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _runtime_expansion_payload_response(_services_module(), payload)
