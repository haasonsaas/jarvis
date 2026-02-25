"""External service tools: smart home, weather, etc.

All destructive actions require confirmation (dry-run by default).
Everything is audit-logged.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import aiohttp
from claude_agent_sdk import tool, create_sdk_mcp_server

from jarvis.config import Config

log = logging.getLogger(__name__)

# Audit log in user's home dir for predictable location
AUDIT_LOG = Path.home() / ".jarvis" / "audit.jsonl"

# Domains that always default to dry_run
SENSITIVE_DOMAINS = {"lock", "alarm_control_panel", "cover"}

_config: Config | None = None


def bind(config: Config) -> None:
    global _config
    _config = config
    # Ensure audit dir exists
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


def _audit(action: str, details: dict) -> None:
    """Append to local audit log: what was heard, what was done, why."""
    entry = {
        "timestamp": time.time(),
        "action": action,
        **details,
    }
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning("Failed to write audit log: %s", e)
    log.info("AUDIT: %s — %s", action, json.dumps(details))


def _now_local() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


# ── Home Assistant ────────────────────────────────────────────

async def smart_home(args: dict[str, Any]) -> dict[str, Any]:
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    domain = args["domain"]
    action = args["action"]
    entity_id = args["entity_id"]
    data = args.get("data", {})
    # Force dry_run for sensitive domains unless explicitly set to false
    dry_run = args.get("dry_run", domain in SENSITIVE_DOMAINS)

    _audit("smart_home", {
        "domain": domain, "action": action, "entity_id": entity_id,
        "data": data, "dry_run": dry_run,
    })

    if dry_run:
        tool_feedback("start")
        return {"content": [{"type": "text", "text": (
            f"DRY RUN: Would call {domain}.{action} on {entity_id}"
            f"{' with ' + json.dumps(data) if data else ''}. "
            f"Set dry_run=false to execute."
        )}]}

    url = f"{_config.hass_url}/api/services/{domain}/{action}"
    headers = {"Authorization": f"Bearer {_config.hass_token}", "Content-Type": "application/json"}
    payload = {"entity_id": entity_id, **data}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        tool_feedback("start")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": f"Done: {domain}.{action} on {entity_id}"}]}
                elif resp.status == 401:
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                elif resp.status == 404:
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": f"Service not found: {domain}.{action}"}]}
                else:
                    text = await resp.text()
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": f"Home Assistant error ({resp.status}): {text[:200]}"}]}
    except aiohttp.ClientError as e:
        tool_feedback("done")
        return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}


async def smart_home_state(args: dict[str, Any]) -> dict[str, Any]:
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        return {"content": [{"type": "text", "text": "Home Assistant not configured."}]}

    url = f"{_config.hass_url}/api/states/{args['entity_id']}"
    headers = {"Authorization": f"Bearer {_config.hass_token}"}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        tool_feedback("start")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": json.dumps({
                        "state": data.get("state", "unknown"),
                        "attributes": data.get("attributes", {}),
                    })}]}
                elif resp.status == 404:
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": f"Entity not found: {args['entity_id']}"}]}
                else:
                    tool_feedback("done")
                    return {"content": [{"type": "text", "text": f"Error ({resp.status}) fetching entity state"}]}
    except aiohttp.ClientError as e:
        tool_feedback("done")
        return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}


async def get_time(args: dict[str, Any]) -> dict[str, Any]:
    from jarvis.tools.robot import tool_feedback
    tool_feedback("start")
    tool_feedback("done")
    return {"content": [{"type": "text", "text": _now_local()}]}


# ── Build MCP server ──────────────────────────────────────────

smart_home_tool = tool(
    "smart_home",
    "Control smart home devices via Home Assistant. "
    "For destructive actions (unlock doors, disable alarms, open covers), set dry_run=true first. "
    "Always explain what you're about to do before executing.",
    {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "HA domain: light, switch, climate, media_player, lock, cover, etc.",
            },
            "action": {
                "type": "string",
                "description": "Service to call: turn_on, turn_off, toggle, set_temperature, etc.",
            },
            "entity_id": {
                "type": "string",
                "description": "Entity ID, e.g. light.living_room, climate.thermostat.",
            },
            "data": {
                "type": "object",
                "description": "Optional service data (brightness, temperature, etc.).",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, describe what would happen without executing. "
                "Always true for locks/alarms/covers unless user explicitly confirms.",
            },
        },
        "required": ["domain", "action", "entity_id"],
    },
)(smart_home)


smart_home_state_tool = tool(
    "smart_home_state",
    "Get the current state of a Home Assistant entity.",
    {"entity_id": str},
)(smart_home_state)


get_time_tool = tool(
    "get_time",
    "Get the current local time (device clock).",
    {},
)(get_time)

def create_services_server():
    return create_sdk_mcp_server(
        name="jarvis-services",
        version="0.1.0",
        tools=[smart_home_tool, smart_home_state_tool, get_time_tool],
    )
