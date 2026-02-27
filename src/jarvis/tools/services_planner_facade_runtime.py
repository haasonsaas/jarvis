"""Planner/automation helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_automation_runtime import (
    apply_ha_automation_config as _runtime_apply_ha_automation_config,
    automation_entry_from_draft as _runtime_automation_entry_from_draft,
    autonomy_tasks as _runtime_autonomy_tasks,
    delete_ha_automation_config as _runtime_delete_ha_automation_config,
    home_plan_from_request as _runtime_home_plan_from_request,
    json_preview as _runtime_json_preview,
    normalize_automation_config as _runtime_normalize_automation_config,
    planner_ready_nodes as _runtime_planner_ready_nodes,
    slugify_identifier as _runtime_slugify_identifier,
    structured_diff as _runtime_structured_diff,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def home_plan_from_request(request_text: str) -> dict[str, Any]:
    return _runtime_home_plan_from_request(request_text)


def slugify_identifier(value: str, *, fallback: str = "item") -> str:
    return _runtime_slugify_identifier(value, fallback=fallback)


def json_preview(value: Any, *, limit: int = 500) -> str:
    return _runtime_json_preview(value, limit=limit)


def structured_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return _runtime_structured_diff(previous, current)


def normalize_automation_config(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    return _runtime_normalize_automation_config(args)


def automation_entry_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return _runtime_automation_entry_from_draft(draft)


async def apply_ha_automation_config(automation_id: str, config_payload: dict[str, Any]) -> tuple[bool, str]:
    return await _runtime_apply_ha_automation_config(_services_module(), automation_id, config_payload)


async def delete_ha_automation_config(automation_id: str) -> tuple[bool, str]:
    return await _runtime_delete_ha_automation_config(_services_module(), automation_id)


def autonomy_tasks() -> list[dict[str, Any]]:
    return _runtime_autonomy_tasks(_services_module())


def planner_ready_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return _runtime_planner_ready_nodes(_services_module(), graph)
