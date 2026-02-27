"""Automation/planning runtime helpers for services domains."""

from __future__ import annotations

import json
import re
from typing import Any


def home_plan_from_request(request_text: str) -> dict[str, Any]:
    text = str(request_text or "").strip().lower()
    if "movie" in text:
        return {
            "label": "movie_mode",
            "steps": [
                {"domain": "light", "action": "turn_off", "entity_id": "light.main_room"},
                {"domain": "light", "action": "turn_on", "entity_id": "light.bias_backlight", "data": {"brightness": 80}},
                {"domain": "media_player", "action": "media_play", "entity_id": "media_player.living_room_tv"},
            ],
        }
    if "bedtime" in text:
        return {
            "label": "bedtime_routine",
            "steps": [
                {"domain": "lock", "action": "lock", "entity_id": "lock.front_door"},
                {"domain": "light", "action": "turn_off", "entity_id": "light.downstairs"},
                {"domain": "climate", "action": "set_temperature", "entity_id": "climate.main", "data": {"temperature": 68}},
            ],
        }
    return {
        "label": "custom",
        "steps": [],
    }


def slugify_identifier(value: str, *, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or fallback


def json_preview(value: Any, *, limit: int = 500) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def structured_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    prev = previous if isinstance(previous, dict) else {}
    curr = current if isinstance(current, dict) else {}
    added = sorted(key for key in curr.keys() if key not in prev)
    removed = sorted(key for key in prev.keys() if key not in curr)
    changed = sorted(
        key
        for key in curr.keys()
        if key in prev and json_preview(prev.get(key)) != json_preview(curr.get(key))
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "has_changes": bool(added or removed or changed),
        "previous_preview": json_preview(prev),
        "current_preview": json_preview(curr),
    }


def normalize_automation_config(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    alias = str(args.get("alias", "")).strip()
    if not alias:
        return None, "alias is required."
    trigger = args.get("trigger") if isinstance(args.get("trigger"), dict) else {}
    conditions = args.get("condition") if isinstance(args.get("condition"), list) else []
    actions = args.get("actions") if isinstance(args.get("actions"), list) else []
    if not trigger:
        return None, "trigger object is required."
    if not actions:
        return None, "actions list is required."
    normalized_actions = [dict(row) for row in actions if isinstance(row, dict)]
    if not normalized_actions:
        return None, "actions list must contain object entries."
    return {
        "alias": alias,
        "trigger": dict(trigger),
        "condition": [dict(row) for row in conditions if isinstance(row, dict)],
        "action": normalized_actions,
        "mode": str(args.get("mode", "single")).strip().lower() or "single",
    }, ""


def automation_entry_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_id": str(draft.get("draft_id", "")),
        "automation_id": str(draft.get("automation_id", "")),
        "alias": str(draft.get("alias", "")),
        "status": str(draft.get("status", "draft")),
        "updated_at": float(draft.get("updated_at", 0.0) or 0.0),
    }


async def apply_ha_automation_config(
    services_module: Any,
    automation_id: str,
    config_payload: dict[str, Any],
) -> tuple[bool, str]:
    s = services_module
    if not s._config or not s._config.has_home_assistant:
        return False, "missing_config"
    path = f"/api/config/automation/config/{automation_id}"
    _, error_code = await s._ha_request_json("PUT", path, payload=config_payload)
    if error_code in {"http_error", "not_found"}:
        _, error_code = await s._ha_request_json("POST", path, payload=config_payload)
    if error_code is not None:
        return False, error_code
    _, reload_error = await s._ha_call_service("automation", "reload", {})
    if reload_error is not None:
        return False, reload_error
    return True, ""


async def delete_ha_automation_config(services_module: Any, automation_id: str) -> tuple[bool, str]:
    s = services_module
    if not s._config or not s._config.has_home_assistant:
        return False, "missing_config"
    path = f"/api/config/automation/config/{automation_id}"
    _, error_code = await s._ha_request_json("DELETE", path)
    if error_code is not None:
        return False, error_code
    _, reload_error = await s._ha_call_service("automation", "reload", {})
    if reload_error is not None:
        return False, reload_error
    return True, ""


def autonomy_tasks(services_module: Any) -> list[dict[str, Any]]:
    s = services_module
    rows: list[dict[str, Any]] = []
    for row in s._deferred_actions.values():
        if not isinstance(row, dict):
            continue
        if str(row.get("kind", "")).strip().lower() != "autonomy_task":
            continue
        rows.append(row)
    return rows


def planner_ready_nodes(services_module: Any, graph: dict[str, Any]) -> list[dict[str, Any]]:
    s = services_module
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, list):
        return []
    status_by_id = {
        str(node.get("id", "")): str(node.get("status", "pending")).strip().lower()
        for node in nodes
        if isinstance(node, dict)
    }
    ready: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("status", "pending")).strip().lower() != "pending":
            continue
        deps = s._as_str_list(node.get("depends_on"), lower=False)
        if all(status_by_id.get(dep, "done") == "done" for dep in deps):
            ready.append(dict(node))
    return ready
