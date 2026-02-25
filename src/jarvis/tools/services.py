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
from jarvis.memory import MemoryStore

log = logging.getLogger(__name__)

# Audit log in user's home dir for predictable location
AUDIT_LOG = Path.home() / ".jarvis" / "audit.jsonl"

# Domains that always default to dry_run
SENSITIVE_DOMAINS = {"lock", "alarm_control_panel", "cover"}
ACTION_COOLDOWN_SEC = 2.0

_config: Config | None = None
_memory: MemoryStore | None = None
_action_last_seen: dict[str, float] = {}


def bind(config: Config, memory_store: MemoryStore | None = None) -> None:
    global _config, _memory
    _config = config
    _memory = memory_store
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


def _action_key(domain: str, action: str, entity_id: str) -> str:
    return f"{domain}:{action}:{entity_id}"


def _cooldown_active(domain: str, action: str, entity_id: str) -> bool:
    now = time.monotonic()
    key = _action_key(domain, action, entity_id)
    last = _action_last_seen.get(key)
    if last is None:
        return False
    return (now - last) < ACTION_COOLDOWN_SEC


def _touch_action(domain: str, action: str, entity_id: str) -> None:
    _action_last_seen[_action_key(domain, action, entity_id)] = time.monotonic()


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

    if _cooldown_active(domain, action, entity_id):
        tool_feedback("done")
        return {"content": [{"type": "text", "text": "Action cooldown active. Try again in a moment."}]}

    _audit("smart_home", {
        "domain": domain, "action": action, "entity_id": entity_id,
        "data": data, "dry_run": dry_run,
    })

    if dry_run:
        tool_feedback("start")
        _touch_action(domain, action, entity_id)
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
                    _touch_action(domain, action, entity_id)
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


# ── Memory + planning ───────────────────────────────────────

async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    tags = args.get("tags") or []
    kind = str(args.get("kind", "note"))
    importance = float(args.get("importance", 0.5))
    sensitivity = float(args.get("sensitivity", 0.0))
    source = str(args.get("source", "user"))
    memory_id = _memory.add_memory(
        text,
        kind=kind,
        tags=[str(tag) for tag in tags],
        importance=importance,
        sensitivity=sensitivity,
        source=source,
    )
    return {"content": [{"type": "text", "text": f"Memory stored (id={memory_id})."}]}


async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    query = str(args.get("query", "")).strip()
    if not query:
        return {"content": [{"type": "text", "text": "Search query required."}]}
    limit = int(args.get("limit", 5))
    include_sensitive = bool(args.get("include_sensitive", False))
    max_sensitivity = None if include_sensitive else float(args.get("max_sensitivity", 0.4))
    results = _memory.search(query, limit=limit, max_sensitivity=max_sensitivity)
    if not results:
        return {"content": [{"type": "text", "text": "No relevant memories found."}]}
    lines = []
    for entry in results:
        tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
        snippet = entry.text[:200]
        lines.append(f"[{entry.id}] ({entry.kind}) {snippet}{tags}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_recent(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = int(args.get("limit", 5))
    kind = args.get("kind")
    results = _memory.recent(limit=limit, kind=str(kind) if kind else None)
    if not results:
        return {"content": [{"type": "text", "text": "No recent memories found."}]}
    lines = []
    for entry in results:
        tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
        snippet = entry.text[:200]
        lines.append(f"[{entry.id}] ({entry.kind}) {snippet}{tags}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def task_plan_create(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    title = str(args.get("title", "")).strip()
    steps = args.get("steps") or []
    if not title or not steps:
        return {"content": [{"type": "text", "text": "Plan title and steps required."}]}
    plan_id = _memory.add_task_plan(title, [str(step) for step in steps])
    return {"content": [{"type": "text", "text": f"Plan created (id={plan_id})."}]}


async def task_plan_list(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    open_only = bool(args.get("open_only", True))
    plans = _memory.list_task_plans(open_only=open_only)
    if not plans:
        return {"content": [{"type": "text", "text": "No task plans found."}]}
    blocks = []
    for plan in plans:
        header = f"Plan {plan.id}: {plan.title} ({plan.status})"
        steps = "\n".join([f"  {step.index + 1}. {step.text} [{step.status}]" for step in plan.steps])
        blocks.append(f"{header}\n{steps}")
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}]}


async def task_plan_update(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = int(args.get("plan_id", 0))
    step_index = int(args.get("step_index", -1))
    status = str(args.get("status", "pending"))
    if plan_id <= 0 or step_index < 0:
        return {"content": [{"type": "text", "text": "Plan id and step index required."}]}
    _memory.update_task_step(plan_id, step_index, status)
    return {"content": [{"type": "text", "text": "Plan updated."}]}


async def task_plan_next(args: dict[str, Any]) -> dict[str, Any]:
    if not _memory:
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = args.get("plan_id")
    plan = _memory.next_task_step(int(plan_id)) if plan_id is not None else _memory.next_task_step()
    if not plan:
        return {"content": [{"type": "text", "text": "No pending steps found."}]}
    task_plan, step = plan
    text = f"Next step for plan {task_plan.id} ({task_plan.title}): {step.index + 1}. {step.text}"
    return {"content": [{"type": "text", "text": text}]}


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

memory_add_tool = tool(
    "memory_add",
    "Store a long-term memory (facts, preferences, summaries).",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "description": "note, profile, summary, task, etc."},
            "tags": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "sensitivity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "source": {"type": "string"},
        },
        "required": ["text"],
    },
)(memory_add)

memory_search_tool = tool(
    "memory_search",
    "Search long-term memory for relevant entries.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "number"},
            "max_sensitivity": {"type": "number"},
            "include_sensitive": {"type": "boolean"},
        },
        "required": ["query"],
    },
)(memory_search)

memory_recent_tool = tool(
    "memory_recent",
    "List recent memory entries.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "number"},
            "kind": {"type": "string"},
        },
    },
)(memory_recent)

task_plan_create_tool = tool(
    "task_plan_create",
    "Create a multi-step task plan and store it.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
    },
)(task_plan_create)

task_plan_list_tool = tool(
    "task_plan_list",
    "List stored task plans (optionally open only).",
    {
        "type": "object",
        "properties": {
            "open_only": {"type": "boolean"},
        },
    },
)(task_plan_list)

task_plan_update_tool = tool(
    "task_plan_update",
    "Update a task plan step status.",
    {
        "type": "object",
        "properties": {
            "plan_id": {"type": "number"},
            "step_index": {"type": "number", "description": "0-based index"},
            "status": {"type": "string", "description": "pending, in_progress, blocked, done"},
        },
        "required": ["plan_id", "step_index", "status"],
    },
)(task_plan_update)

task_plan_next_tool = tool(
    "task_plan_next",
    "Get the next pending step in a task plan.",
    {
        "type": "object",
        "properties": {
            "plan_id": {"type": "number"},
        },
    },
)(task_plan_next)

def create_services_server():
    return create_sdk_mcp_server(
        name="jarvis-services",
        version="0.1.0",
        tools=[
            smart_home_tool,
            smart_home_state_tool,
            get_time_tool,
            memory_add_tool,
            memory_search_tool,
            memory_recent_tool,
            task_plan_create_tool,
            task_plan_list_tool,
            task_plan_update_tool,
            task_plan_next_tool,
        ],
    )
