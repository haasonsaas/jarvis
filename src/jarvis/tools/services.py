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
from jarvis.tool_policy import is_tool_allowed
from jarvis.tool_summary import record_summary, list_summaries
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
_tool_allowlist: list[str] = []
_tool_denylist: list[str] = []
_audit_log_max_bytes: int = 1_000_000
_audit_log_backups: int = 3


def bind(config: Config, memory_store: MemoryStore | None = None) -> None:
    global _config, _memory, _audit_log_max_bytes, _audit_log_backups
    _config = config
    _memory = memory_store
    _audit_log_max_bytes = int(config.audit_log_max_bytes)
    _audit_log_backups = int(config.audit_log_backups)
    global _tool_allowlist, _tool_denylist
    _tool_allowlist = list(config.tool_allowlist)
    _tool_denylist = list(config.tool_denylist)
    # Ensure audit dir exists
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


def _tool_permitted(name: str) -> bool:
    if _config is not None and not _config.home_enabled:
        if name in {"smart_home", "smart_home_state"}:
            return False
    return is_tool_allowed(name, _tool_allowlist, _tool_denylist)


def _audit(action: str, details: dict) -> None:
    """Append to local audit log: what was heard, what was done, why."""
    details_json = json.dumps(details, default=str)
    entry = {
        "timestamp": time.time(),
        "action": action,
        **details,
    }
    try:
        _rotate_audit_log_if_needed()
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        log.warning("Failed to write audit log: %s", e)
    log.info("AUDIT: %s — %s", action, details_json)


def _rotate_audit_log_if_needed() -> None:
    if _audit_log_backups < 1:
        return
    try:
        if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size >= _audit_log_max_bytes:
            for idx in range(_audit_log_backups, 0, -1):
                src = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx}")
                dst = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx + 1}")
                if src.exists():
                    if idx == _audit_log_backups:
                        src.unlink(missing_ok=True)
                    else:
                        src.rename(dst)
            rotated = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.1")
            AUDIT_LOG.rename(rotated)
    except OSError as e:
        log.warning("Failed to rotate audit log: %s", e)


def _format_tool_summaries(items: list[dict[str, object]]) -> str:
    if not items:
        return "No recent tool activity."
    lines = []
    for item in items:
        name = str(item.get("name", "tool"))
        status = str(item.get("status", "unknown"))
        duration = float(item.get("duration_ms", 0.0))
        detail = item.get("detail")
        detail_text = f" ({detail})" if detail else ""
        lines.append(f"- {name}: {status} ({duration:.0f}ms){detail_text}")
    return "\n".join(lines)


def _now_local() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _as_bool(value: Any, default: bool = False) -> bool:
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
        return bool(value)
    return default


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or None
    text = str(value).strip()
    return [text] if text else None


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


def _audit_status() -> dict[str, Any]:
    exists = AUDIT_LOG.exists()
    size_bytes = AUDIT_LOG.stat().st_size if exists else 0
    backups = []
    for idx in range(1, _audit_log_backups + 1):
        backup_path = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx}")
        if backup_path.exists():
            backups.append(
                {
                    "path": str(backup_path),
                    "size_bytes": int(backup_path.stat().st_size),
                }
            )
    return {
        "path": str(AUDIT_LOG),
        "exists": exists,
        "size_bytes": int(size_bytes),
        "max_bytes": int(_audit_log_max_bytes),
        "backups": backups,
    }


# ── Home Assistant ────────────────────────────────────────────

async def smart_home(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("smart_home"):
        record_summary("smart_home", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        record_summary("smart_home", "error", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    domain = str(args.get("domain", "")).strip()
    action = str(args.get("action", "")).strip()
    entity_id = str(args.get("entity_id", "")).strip()
    data = args.get("data", {})
    if not domain or not action or not entity_id:
        record_summary("smart_home", "error", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Domain, action, and entity_id are required."}]}
    if not isinstance(data, dict):
        record_summary("smart_home", "error", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Service data must be an object."}]}
    # Force dry_run for sensitive domains unless explicitly set to false
    dry_run = _as_bool(args.get("dry_run"), default=domain in SENSITIVE_DOMAINS)

    if _cooldown_active(domain, action, entity_id):
        tool_feedback("done")
        record_summary("smart_home", "cooldown", start_time)
        return {"content": [{"type": "text", "text": "Action cooldown active. Try again in a moment."}]}

    _audit("smart_home", {
        "domain": domain, "action": action, "entity_id": entity_id,
        "data": data, "dry_run": dry_run,
    })

    if dry_run:
        tool_feedback("start")
        tool_feedback("done")
        _touch_action(domain, action, entity_id)
        record_summary("smart_home", "dry_run", start_time)
        return {"content": [{"type": "text", "text": (
            f"DRY RUN: Would call {domain}.{action} on {entity_id}"
            f"{' with ' + json.dumps(data, default=str) if data else ''}. "
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
                    record_summary("smart_home", "ok", start_time)
                    return {"content": [{"type": "text", "text": f"Done: {domain}.{action} on {entity_id}"}]}
                elif resp.status == 401:
                    tool_feedback("done")
                    record_summary("smart_home", "error", start_time, "auth")
                    return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                elif resp.status == 404:
                    tool_feedback("done")
                    record_summary("smart_home", "error", start_time, "not_found")
                    return {"content": [{"type": "text", "text": f"Service not found: {domain}.{action}"}]}
                else:
                    text = await resp.text()
                    tool_feedback("done")
                    record_summary("smart_home", "error", start_time, f"http_{resp.status}")
                    return {"content": [{"type": "text", "text": f"Home Assistant error ({resp.status}): {text[:200]}"}]}
    except aiohttp.ClientError as e:
        tool_feedback("done")
        record_summary("smart_home", "error", start_time, str(e))
        return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}
    except Exception as e:
        tool_feedback("done")
        record_summary("smart_home", "error", start_time, "unexpected")
        log.exception("Unexpected smart_home failure")
        return {"content": [{"type": "text", "text": f"Unexpected Home Assistant error: {e}"}]}


async def smart_home_state(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("smart_home_state"):
        record_summary("smart_home_state", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        record_summary("smart_home_state", "error", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured."}]}

    entity_id = str(args.get("entity_id", "")).strip()
    if not entity_id:
        record_summary("smart_home_state", "error", start_time, "missing_entity")
        return {"content": [{"type": "text", "text": "Entity id required."}]}

    url = f"{_config.hass_url}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {_config.hass_token}"}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        tool_feedback("start")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tool_feedback("done")
                    record_summary("smart_home_state", "ok", start_time)
                    return {"content": [{"type": "text", "text": json.dumps({
                        "state": data.get("state", "unknown"),
                        "attributes": data.get("attributes", {}),
                    })}]}
                elif resp.status == 404:
                    tool_feedback("done")
                    record_summary("smart_home_state", "error", start_time, "not_found")
                    return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
                else:
                    tool_feedback("done")
                    record_summary("smart_home_state", "error", start_time, f"http_{resp.status}")
                    return {"content": [{"type": "text", "text": f"Error ({resp.status}) fetching entity state"}]}
    except aiohttp.ClientError as e:
        tool_feedback("done")
        record_summary("smart_home_state", "error", start_time, str(e))
        return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}
    except Exception as e:
        tool_feedback("done")
        record_summary("smart_home_state", "error", start_time, "unexpected")
        log.exception("Unexpected smart_home_state failure")
        return {"content": [{"type": "text", "text": f"Unexpected Home Assistant error: {e}"}]}


async def get_time(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("get_time"):
        record_summary("get_time", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback
    tool_feedback("start")
    tool_feedback("done")
    record_summary("get_time", "ok", start_time)
    return {"content": [{"type": "text", "text": _now_local()}]}


async def system_status(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("system_status"):
        record_summary("system_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    memory_status = None
    if _memory is not None:
        try:
            memory_status = _memory.memory_status()
        except Exception as e:
            memory_status = {"error": str(e)}

    status = {
        "local_time": _now_local(),
        "home_assistant_configured": bool(_config and _config.has_home_assistant),
        "motion_enabled": bool(_config and _config.motion_enabled),
        "home_tools_enabled": bool(_config and _config.home_enabled),
        "memory_enabled": bool(_config and _config.memory_enabled),
        "backchannel_style": _config.backchannel_style if _config else "unknown",
        "tool_policy": {
            "allow_count": len(_tool_allowlist),
            "deny_count": len(_tool_denylist),
        },
        "memory": memory_status,
        "audit": _audit_status(),
        "recent_tools": list_summaries(limit=5),
    }
    record_summary("system_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status)}]}


# ── Memory + planning ───────────────────────────────────────

async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_add"):
        record_summary("memory_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("memory_add", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        record_summary("memory_add", "error", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    tags_raw = args.get("tags")
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    kind = str(args.get("kind", "note"))
    importance = _as_float(args.get("importance", 0.5), 0.5, minimum=0.0, maximum=1.0)
    sensitivity = _as_float(args.get("sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    source = str(args.get("source", "user"))
    memory_id = _memory.add_memory(
        text,
        kind=kind,
        tags=tags,
        importance=importance,
        sensitivity=sensitivity,
        source=source,
    )
    record_summary("memory_add", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Memory stored (id={memory_id})."}]}


async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_search"):
        record_summary("memory_search", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("memory_search", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    query = str(args.get("query", "")).strip()
    if not query:
        record_summary("memory_search", "error", start_time, "missing_query")
        return {"content": [{"type": "text", "text": "Search query required."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    include_sensitive = _as_bool(args.get("include_sensitive"), default=False)
    max_sensitivity = None if include_sensitive else _as_float(args.get("max_sensitivity", 0.4), 0.4, minimum=0.0, maximum=1.0)
    source_list = _as_str_list(args.get("sources"))
    results = _memory.search_v2(
        query,
        limit=limit,
        max_sensitivity=max_sensitivity,
        hybrid_weight=_as_float(args.get("hybrid_weight", 0.7), 0.7, minimum=0.0, maximum=1.0),
        decay_enabled=_as_bool(args.get("decay_enabled"), default=False),
        decay_half_life_days=_as_float(args.get("decay_half_life_days", 30.0), 30.0, minimum=0.1),
        mmr_enabled=_as_bool(args.get("mmr_enabled"), default=False),
        mmr_lambda=_as_float(args.get("mmr_lambda", 0.7), 0.7, minimum=0.0, maximum=1.0),
        sources=source_list,
    )
    if not results:
        record_summary("memory_search", "empty", start_time)
        return {"content": [{"type": "text", "text": "No relevant memories found."}]}
    lines = []
    for entry in results:
        tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
        snippet = entry.text[:200]
        lines.append(f"[{entry.id}] ({entry.kind}) {snippet}{tags}")
    record_summary("memory_search", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_status(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_status"):
        record_summary("memory_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("memory_status", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    if _as_bool(args.get("warm"), default=False):
        _memory.warm()
    if _as_bool(args.get("sync"), default=False):
        _memory.sync()
    status = _memory.memory_status()
    record_summary("memory_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status)}]}


async def memory_recent(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_recent"):
        record_summary("memory_recent", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("memory_recent", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    kind = args.get("kind")
    source_list = _as_str_list(args.get("sources"))
    results = _memory.recent(limit=limit, kind=str(kind) if kind else None, sources=source_list)
    if not results:
        record_summary("memory_recent", "empty", start_time)
        return {"content": [{"type": "text", "text": "No recent memories found."}]}
    lines = []
    for entry in results:
        tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
        snippet = entry.text[:200]
        lines.append(f"[{entry.id}] ({entry.kind}) {snippet}{tags}")
    record_summary("memory_recent", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_summary_add(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_add"):
        record_summary("memory_summary_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("memory_summary_add", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    topic = str(args.get("topic", "")).strip()
    summary = str(args.get("summary", "")).strip()
    if not topic or not summary:
        record_summary("memory_summary_add", "error", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Summary topic and text required."}]}
    _memory.upsert_summary(topic, summary)
    record_summary("memory_summary_add", "ok", start_time)
    return {"content": [{"type": "text", "text": "Summary stored."}]}


async def memory_summary_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_list"):
        record_summary("memory_summary_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("memory_summary_list", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    results = _memory.list_summaries(limit=limit)
    if not results:
        record_summary("memory_summary_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No summaries found."}]}
    lines = [f"{summary.topic}: {summary.summary}" for summary in results]
    record_summary("memory_summary_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def task_plan_create(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_create"):
        record_summary("task_plan_create", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("task_plan_create", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    title = str(args.get("title", "")).strip()
    steps = args.get("steps")
    if not title or not isinstance(steps, list) or not steps:
        record_summary("task_plan_create", "error", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan title and steps required."}]}
    try:
        plan_id = _memory.add_task_plan(title, [str(step) for step in steps])
    except ValueError:
        record_summary("task_plan_create", "error", start_time, "invalid_steps")
        return {"content": [{"type": "text", "text": "Plan requires at least one non-empty step."}]}
    record_summary("task_plan_create", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Plan created (id={plan_id})."}]}


async def task_plan_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_list"):
        record_summary("task_plan_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("task_plan_list", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    open_only = _as_bool(args.get("open_only"), default=True)
    plans = _memory.list_task_plans(open_only=open_only)
    if not plans:
        record_summary("task_plan_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No task plans found."}]}
    blocks = []
    for plan in plans:
        header = f"Plan {plan.id}: {plan.title} ({plan.status})"
        steps = "\n".join([f"  {step.index + 1}. {step.text} [{step.status}]" for step in plan.steps])
        blocks.append(f"{header}\n{steps}")
    record_summary("task_plan_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}]}


async def task_plan_update(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_update"):
        record_summary("task_plan_update", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("task_plan_update", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_int(args.get("plan_id", 0), 0)
    step_index = _as_int(args.get("step_index", -1), -1)
    status = str(args.get("status", "pending")).strip()
    allowed_status = {"pending", "in_progress", "blocked", "done"}
    if plan_id <= 0 or step_index < 0:
        record_summary("task_plan_update", "error", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan id and step index required."}]}
    if status not in allowed_status:
        record_summary("task_plan_update", "error", start_time, "invalid_status")
        return {"content": [{"type": "text", "text": "Status must be one of: pending, in_progress, blocked, done."}]}
    updated = _memory.update_task_step(plan_id, step_index, status)
    if not updated:
        record_summary("task_plan_update", "empty", start_time)
        return {"content": [{"type": "text", "text": "No task step updated."}]}
    record_summary("task_plan_update", "ok", start_time)
    return {"content": [{"type": "text", "text": "Plan updated."}]}


async def task_plan_summary(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_summary"):
        record_summary("task_plan_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("task_plan_summary", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_int(args.get("plan_id", 0), 0)
    if plan_id <= 0:
        record_summary("task_plan_summary", "error", start_time, "missing_plan")
        return {"content": [{"type": "text", "text": "Plan id required."}]}
    progress = _memory.task_plan_progress(plan_id)
    if not progress:
        record_summary("task_plan_summary", "empty", start_time)
        return {"content": [{"type": "text", "text": "Plan not found."}]}
    done, total = progress
    text = f"Plan {plan_id}: {done}/{total} steps complete."
    record_summary("task_plan_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


async def task_plan_next(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_next"):
        record_summary("task_plan_next", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        record_summary("task_plan_next", "error", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = args.get("plan_id")
    if plan_id is not None and _as_int(plan_id, 0) <= 0:
        record_summary("task_plan_next", "error", start_time, "invalid_plan")
        return {"content": [{"type": "text", "text": "Plan id must be a positive integer."}]}
    parsed_plan_id = _as_int(plan_id, 0) if plan_id is not None else None
    plan = _memory.next_task_step(parsed_plan_id) if parsed_plan_id else _memory.next_task_step()
    if not plan:
        record_summary("task_plan_next", "empty", start_time)
        return {"content": [{"type": "text", "text": "No pending steps found."}]}
    task_plan, step = plan
    text = f"Next step for plan {task_plan.id} ({task_plan.title}): {step.index + 1}. {step.text}"
    record_summary("task_plan_next", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


async def tool_summary(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("tool_summary"):
        record_summary("tool_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=100)
    summaries = list_summaries(limit)
    record_summary("tool_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(summaries)}]}


async def tool_summary_text(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("tool_summary_text"):
        record_summary("tool_summary_text", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 6), 6, minimum=1, maximum=100)
    summaries = list_summaries(limit)
    text = _format_tool_summaries(summaries)
    record_summary("tool_summary_text", "ok", start_time)
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

system_status_tool = tool(
    "system_status",
    "Report current runtime capabilities and health snapshot.",
    {},
)(system_status)

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
            "hybrid_weight": {"type": "number"},
            "decay_enabled": {"type": "boolean"},
            "decay_half_life_days": {"type": "number"},
            "mmr_enabled": {"type": "boolean"},
            "mmr_lambda": {"type": "number"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
    },
)(memory_search)

memory_status_tool = tool(
    "memory_status",
    "Report memory index status and availability.",
    {
        "type": "object",
        "properties": {
            "warm": {"type": "boolean"},
            "sync": {"type": "boolean"},
        },
    },
)(memory_status)

memory_recent_tool = tool(
    "memory_recent",
    "List recent memory entries.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "number"},
            "kind": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
    },
)(memory_recent)

memory_summary_add_tool = tool(
    "memory_summary_add",
    "Store or update a short memory summary for a topic.",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["topic", "summary"],
    },
)(memory_summary_add)

memory_summary_list_tool = tool(
    "memory_summary_list",
    "List recent memory summaries.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "number"},
        },
    },
)(memory_summary_list)

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

task_plan_summary_tool = tool(
    "task_plan_summary",
    "Summarize progress for a task plan.",
    {
        "type": "object",
        "properties": {
            "plan_id": {"type": "number"},
        },
        "required": ["plan_id"],
    },
)(task_plan_summary)

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

tool_summary_tool = tool(
    "tool_summary",
    "Return recent tool execution summaries (latency/outcome).",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "number"},
        },
    },
)(tool_summary)

tool_summary_text_tool = tool(
    "tool_summary_text",
    "Summarize recent tool executions for the user.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "number"},
        },
    },
)(tool_summary_text)

def create_services_server():
    return create_sdk_mcp_server(
        name="jarvis-services",
        version="0.1.0",
        tools=[
            smart_home_tool,
            smart_home_state_tool,
            get_time_tool,
            system_status_tool,
            tool_summary_tool,
            tool_summary_text_tool,
            memory_add_tool,
            memory_search_tool,
            memory_recent_tool,
            memory_status_tool,
            memory_summary_add_tool,
            memory_summary_list_tool,
            task_plan_create_tool,
            task_plan_list_tool,
            task_plan_update_tool,
            task_plan_summary_tool,
            task_plan_next_tool,
        ],
    )
