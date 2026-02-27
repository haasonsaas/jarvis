"""Residual core helper extraction for `jarvis.tools.services`."""

from __future__ import annotations

import math
import time
from typing import Any, Callable

from jarvis.tool_policy import is_tool_allowed
from jarvis.tools.service_policy import SAFE_MODE_BLOCKED_TOOLS


def record_service_error(
    services: Any,
    tool_name: str,
    start_time: float,
    code: str,
    *,
    normalize_service_error_code_fn: Callable[[str], str],
    record_summary_fn: Callable[..., None],
) -> None:
    normalized = normalize_service_error_code_fn(code)
    integration = services._integration_for_tool(tool_name)
    if integration is not None:
        services._integration_record_failure(integration, normalized)
    record_summary_fn(tool_name, "error", start_time, normalized)


def tool_permitted(services: Any, name: str) -> bool:
    if services._safe_mode_enabled and name in SAFE_MODE_BLOCKED_TOOLS:
        return False
    if services._home_permission_profile == "readonly" and name in {"smart_home", "media_control"}:
        return False
    if services._todoist_permission_profile == "readonly" and name == "todoist_add_task":
        return False
    if services._email_permission_profile == "readonly" and name == "email_send":
        return False
    if services._notification_permission_profile == "off" and name in {"pushover_notify", "slack_notify", "discord_notify"}:
        return False
    if (
        name.startswith("skills_")
        and name != "skills_list"
        and services._skill_registry is not None
        and not services._skill_registry.enabled
    ):
        return False
    if services._config is not None and not services._config.home_enabled:
        if name in {
            "smart_home",
            "smart_home_state",
            "home_assistant_capabilities",
            "home_assistant_conversation",
            "home_assistant_todo",
            "home_assistant_timer",
            "home_assistant_area_entities",
            "media_control",
            "calendar_events",
            "calendar_next_event",
        }:
            return False
    return is_tool_allowed(name, services._tool_allowlist, services._tool_denylist)


def format_tool_summaries(items: list[dict[str, object]]) -> str:
    if not items:
        return "No recent tool activity."
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "tool"))
        status = str(item.get("status", "unknown"))
        try:
            duration = float(item.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        if not math.isfinite(duration):
            duration = 0.0
        detail = item.get("detail")
        effect = item.get("effect")
        risk = item.get("risk")
        detail_text = f" ({detail})" if detail else ""
        effect_text = f" effect={effect}" if effect else ""
        risk_text = f" risk={risk}" if risk else ""
        lines.append(f"- {name}: {status} ({duration:.0f}ms){detail_text}{effect_text}{risk_text}")
    if not lines:
        return "No recent tool activity."
    return "\n".join(lines)


def now_local() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
