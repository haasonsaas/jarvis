"""External service tools: smart home, weather, etc.

All destructive actions require confirmation (dry-run by default).
Everything is audit-logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from pathlib import Path
from typing import Any

import aiohttp
from claude_agent_sdk import tool, create_sdk_mcp_server

from jarvis.config import Config
from jarvis.tool_policy import is_tool_allowed
from jarvis.tool_summary import record_summary, list_summaries
from jarvis.memory import MemoryStore
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES, normalize_service_error_code

log = logging.getLogger(__name__)

# Audit log in user's home dir for predictable location
AUDIT_LOG = Path.home() / ".jarvis" / "audit.jsonl"

# Domains that always default to dry_run
SENSITIVE_DOMAINS = {"lock", "alarm_control_panel", "cover", "climate"}
ACTION_COOLDOWN_SEC = 2.0
ACTION_HISTORY_RETENTION_SEC = 3600.0
ACTION_HISTORY_MAX_ENTRIES = 2000
HA_STATE_CACHE_TTL_SEC = 2.0
HA_MUTATING_ALLOWED_ACTIONS: dict[str, set[str]] = {
    "light": {"turn_on", "turn_off", "toggle"},
    "switch": {"turn_on", "turn_off", "toggle"},
    "lock": {"lock", "unlock"},
    "cover": {"open_cover", "close_cover", "stop_cover"},
    "climate": {"set_temperature", "set_hvac_mode", "set_fan_mode"},
    "media_player": {"turn_on", "turn_off", "toggle", "volume_set", "media_play", "media_pause", "play_media"},
    "alarm_control_panel": {"arm_home", "arm_away", "disarm"},
}
TODOIST_LIST_MAX_RETRIES = 2
RETRY_BASE_DELAY_SEC = 0.2
RETRY_MAX_DELAY_SEC = 1.0
RETRY_JITTER_RATIO = 0.2

_config: Config | None = None
_memory: MemoryStore | None = None
_action_last_seen: dict[str, float] = {}
_tool_allowlist: list[str] = []
_tool_denylist: list[str] = []
_audit_log_max_bytes: int = 1_000_000
_audit_log_backups: int = 3
_home_permission_profile: str = "control"
_home_require_confirm_execute: bool = False
_todoist_permission_profile: str = "control"
_notification_permission_profile: str = "allow"
_todoist_timeout_sec: float = 10.0
_pushover_timeout_sec: float = 10.0
_ha_state_cache: dict[str, tuple[float, dict[str, Any]]] = {}
SENSITIVE_AUDIT_KEY_TOKENS = {
    "code",
    "pin",
    "password",
    "token",
    "secret",
    "alarm_code",
    "passcode",
    "webhook_id",
    "oauth_token",
    "api_key",
    "access_token",
    "authorization",
}
AUDIT_REDACTED = "***REDACTED***"
AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS: dict[str, set[str]] = {
    "todoist_add_task": {"content", "description", "due_string", "message", "title"},
    "todoist_list_tasks": {"content", "description", "due_string", "message", "title"},
    "pushover_notify": {"message", "title", "content", "description", "body"},
}

SERVICE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "smart_home": {
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
    "smart_home_state": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
        },
        "required": ["entity_id"],
    },
    "todoist_add_task": {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "description": {"type": "string"},
            "due_string": {"type": "string"},
            "priority": {"type": "integer"},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["content"],
    },
    "todoist_list_tasks": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "format": {"type": "string", "description": "short (default) or verbose"},
        },
    },
    "pushover_notify": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "title": {"type": "string"},
            "priority": {"type": "integer"},
        },
        "required": ["message"],
    },
    "get_time": {},
    "system_status": {},
    "memory_add": {
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
    "memory_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
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
    "memory_status": {
        "type": "object",
        "properties": {
            "warm": {"type": "boolean"},
            "sync": {"type": "boolean"},
            "optimize": {"type": "boolean"},
            "vacuum": {"type": "boolean"},
        },
    },
    "memory_recent": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "kind": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
    },
    "memory_summary_add": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["topic", "summary"],
    },
    "memory_summary_list": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "task_plan_create": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
    },
    "task_plan_list": {
        "type": "object",
        "properties": {
            "open_only": {"type": "boolean"},
        },
    },
    "task_plan_update": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
            "step_index": {"type": "integer", "description": "0-based index"},
            "status": {"type": "string", "description": "pending, in_progress, blocked, done"},
        },
        "required": ["plan_id", "step_index", "status"],
    },
    "task_plan_summary": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
        },
        "required": ["plan_id"],
    },
    "task_plan_next": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
        },
    },
    "tool_summary": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "tool_summary_text": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
}

SERVICE_RUNTIME_REQUIRED_FIELDS: dict[str, set[str]] = {
    "smart_home": {"domain", "action", "entity_id"},
    "smart_home_state": {"entity_id"},
    "todoist_add_task": {"content"},
    "todoist_list_tasks": set(),
    "pushover_notify": {"message"},
    "get_time": set(),
    "system_status": set(),
    "memory_add": {"text"},
    "memory_search": {"query"},
    "memory_status": set(),
    "memory_recent": set(),
    "memory_summary_add": {"topic", "summary"},
    "memory_summary_list": set(),
    "task_plan_create": {"title", "steps"},
    "task_plan_list": set(),
    "task_plan_update": {"plan_id", "step_index", "status"},
    "task_plan_summary": {"plan_id"},
    "task_plan_next": set(),
    "tool_summary": set(),
    "tool_summary_text": set(),
}

# Backward compatibility for existing imports/tests.
SERVICE_ERROR_CODES = TOOL_SERVICE_ERROR_CODES


def _record_service_error(tool_name: str, start_time: float, code: str) -> None:
    normalized = normalize_service_error_code(code)
    record_summary(tool_name, "error", start_time, normalized)


def bind(config: Config, memory_store: MemoryStore | None = None) -> None:
    global _config, _memory, _audit_log_max_bytes, _audit_log_backups
    global _home_permission_profile, _home_require_confirm_execute, _todoist_permission_profile, _notification_permission_profile
    global _todoist_timeout_sec, _pushover_timeout_sec
    _config = config
    _memory = memory_store
    _audit_log_max_bytes = int(config.audit_log_max_bytes)
    _audit_log_backups = int(config.audit_log_backups)
    _home_permission_profile = str(getattr(config, "home_permission_profile", "control")).strip().lower()
    if _home_permission_profile not in {"readonly", "control"}:
        _home_permission_profile = "control"
    _home_require_confirm_execute = bool(getattr(config, "home_require_confirm_execute", False))
    _todoist_permission_profile = str(getattr(config, "todoist_permission_profile", "control")).strip().lower()
    if _todoist_permission_profile not in {"readonly", "control"}:
        _todoist_permission_profile = "control"
    _notification_permission_profile = str(
        getattr(config, "notification_permission_profile", "allow")
    ).strip().lower()
    if _notification_permission_profile not in {"off", "allow"}:
        _notification_permission_profile = "allow"
    _todoist_timeout_sec = float(getattr(config, "todoist_timeout_sec", 10.0))
    _pushover_timeout_sec = float(getattr(config, "pushover_timeout_sec", 10.0))
    _action_last_seen.clear()
    _ha_state_cache.clear()
    global _tool_allowlist, _tool_denylist
    _tool_allowlist = list(config.tool_allowlist)
    _tool_denylist = list(config.tool_denylist)
    # Ensure audit dir exists
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


def _tool_permitted(name: str) -> bool:
    if _home_permission_profile == "readonly" and name == "smart_home":
        return False
    if _todoist_permission_profile == "readonly" and name == "todoist_add_task":
        return False
    if _notification_permission_profile == "off" and name == "pushover_notify":
        return False
    if _config is not None and not _config.home_enabled:
        if name in {"smart_home", "smart_home_state"}:
            return False
    return is_tool_allowed(name, _tool_allowlist, _tool_denylist)


def _audit(action: str, details: dict) -> None:
    """Append to local audit log: what was heard, what was done, why."""
    metadata_only = _metadata_only_audit_details(action, details)
    redacted = _redact_sensitive_for_audit(metadata_only)
    details_json = json.dumps(redacted, default=str)
    entry = {
        "timestamp": time.time(),
        "action": action,
        **redacted,
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


def _redact_sensitive_for_audit(value: Any, *, key_hint: str | None = None) -> Any:
    if key_hint:
        lowered = key_hint.strip().lower()
        if any(token in lowered for token in SENSITIVE_AUDIT_KEY_TOKENS):
            return AUDIT_REDACTED
    if isinstance(value, dict):
        return {
            str(key): _redact_sensitive_for_audit(item, key_hint=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_for_audit(item, key_hint=key_hint) for item in value]
    return value


def _metadata_only_audit_details(action: str, details: dict[str, Any]) -> dict[str, Any]:
    forbidden = AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS.get(action)
    if not forbidden:
        return {str(key): value for key, value in details.items()}
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        key_text = str(key)
        if key_text.strip().lower() in forbidden:
            continue
        sanitized[key_text] = value
    return sanitized


def _format_tool_summaries(items: list[dict[str, object]]) -> str:
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
        if isinstance(value, float) and not math.isfinite(value):
            return default
        return bool(value)
    return default


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
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


def _as_exact_int(value: Any) -> int | None:
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


def _as_float(
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


def _retry_backoff_delay(
    attempt_index: int,
    *,
    base_delay_sec: float = RETRY_BASE_DELAY_SEC,
    max_delay_sec: float = RETRY_MAX_DELAY_SEC,
    jitter_ratio: float = RETRY_JITTER_RATIO,
    jitter_sample: float | None = None,
) -> float:
    step = max(0, int(attempt_index))
    base_delay = min(max_delay_sec, base_delay_sec * (2 ** step))
    sample = random.random() if jitter_sample is None else float(jitter_sample)
    sample = min(1.0, max(0.0, sample))
    jitter = base_delay * jitter_ratio * ((sample * 2.0) - 1.0)
    return max(0.0, base_delay + jitter)


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


def _prune_action_history(now: float | None = None) -> None:
    if not _action_last_seen:
        return
    current = time.monotonic() if now is None else now
    cutoff = current - ACTION_HISTORY_RETENTION_SEC
    stale_keys = [key for key, ts in _action_last_seen.items() if ts < cutoff]
    for key in stale_keys:
        _action_last_seen.pop(key, None)
    if len(_action_last_seen) <= ACTION_HISTORY_MAX_ENTRIES:
        return
    over = len(_action_last_seen) - ACTION_HISTORY_MAX_ENTRIES
    oldest = sorted(_action_last_seen.items(), key=lambda item: item[1])[:over]
    for key, _ in oldest:
        _action_last_seen.pop(key, None)


def _cooldown_active(domain: str, action: str, entity_id: str) -> bool:
    now = time.monotonic()
    _prune_action_history(now)
    key = _action_key(domain, action, entity_id)
    last = _action_last_seen.get(key)
    if last is None:
        return False
    return (now - last) < ACTION_COOLDOWN_SEC


def _touch_action(domain: str, action: str, entity_id: str) -> None:
    now = time.monotonic()
    _action_last_seen[_action_key(domain, action, entity_id)] = now
    _prune_action_history(now)


def _audit_status() -> dict[str, Any]:
    try:
        exists = AUDIT_LOG.exists()
        size_bytes = AUDIT_LOG.stat().st_size if exists else 0
    except OSError:
        exists = False
        size_bytes = 0
    backups = []
    for idx in range(1, _audit_log_backups + 1):
        backup_path = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{idx}")
        try:
            if backup_path.exists():
                backups.append(
                    {
                        "path": str(backup_path),
                        "size_bytes": int(backup_path.stat().st_size),
                    }
                )
        except OSError:
            continue
    return {
        "path": str(AUDIT_LOG),
        "exists": exists,
        "size_bytes": int(size_bytes),
        "max_bytes": int(_audit_log_max_bytes),
        "backups": backups,
        "redaction_enabled": bool(SENSITIVE_AUDIT_KEY_TOKENS),
        "redaction_key_count": len(SENSITIVE_AUDIT_KEY_TOKENS),
        "metadata_only_actions": sorted(AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS),
    }


def _ha_headers() -> dict[str, str]:
    assert _config is not None
    return {"Authorization": f"Bearer {_config.hass_token}"}


def _ha_cached_state(entity_id: str) -> dict[str, Any] | None:
    item = _ha_state_cache.get(entity_id)
    if item is None:
        return None
    expires_at, payload = item
    if expires_at < time.monotonic():
        _ha_state_cache.pop(entity_id, None)
        return None
    return payload


def _ha_invalidate_state(entity_id: str) -> None:
    _ha_state_cache.pop(entity_id, None)


def _ha_action_allowed(domain: str, action: str) -> bool:
    allowed = HA_MUTATING_ALLOWED_ACTIONS.get(domain)
    if allowed is None:
        return False
    return action in allowed


async def _ha_get_state(entity_id: str) -> tuple[dict[str, Any] | None, str | None]:
    cached = _ha_cached_state(entity_id)
    if cached is not None:
        return cached, None
    assert _config is not None
    url = f"{_config.hass_url}/api/states/{entity_id}"
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=_ha_headers()) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(data, dict):
                        return None, "invalid_json"
                    _ha_state_cache[entity_id] = (time.monotonic() + HA_STATE_CACHE_TTL_SEC, data)
                    return data, None
                if resp.status == 401:
                    return None, "auth"
                if resp.status == 404:
                    return None, "not_found"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"


def _health_rollup(
    *,
    config_present: bool,
    memory_status: dict[str, Any] | None,
    recent_tools: list[dict[str, object]] | dict[str, str],
) -> dict[str, Any]:
    reasons: list[str] = []
    level = "ok"
    if not config_present:
        level = "error"
        reasons.append("config_unbound")
    if isinstance(memory_status, dict) and "error" in memory_status:
        reasons.append("memory_error")
    if isinstance(recent_tools, dict) and "error" in recent_tools:
        reasons.append("tool_summary_error")
    if reasons and level != "error":
        level = "degraded"
    return {"health_level": level, "reasons": reasons}


# ── Home Assistant ────────────────────────────────────────────

async def smart_home(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("smart_home"):
        record_summary("smart_home", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        _record_service_error("smart_home", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    domain = str(args.get("domain", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    data = args.get("data", {})
    if not domain or not entity_id:
        _record_service_error("smart_home", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Domain and entity_id are required."}]}
    if not action or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in action):
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Action must be a non-empty snake_case service name."}]}
    if not isinstance(data, dict):
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "Service data must be an object."}]}
    if domain not in HA_MUTATING_ALLOWED_ACTIONS:
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Unsupported domain for smart_home: {domain}"}]}
    entity_domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    if not entity_domain or entity_domain != domain:
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "entity_id domain must match domain."}]}
    if not _ha_action_allowed(domain, action):
        _record_service_error("smart_home", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": f"Unsupported action for domain: {domain}.{action}"}]}
    # Force dry_run for sensitive domains unless explicitly set to false
    dry_run = _as_bool(args.get("dry_run"), default=domain in SENSITIVE_DOMAINS)
    confirm = _as_bool(args.get("confirm"), default=False)
    if _home_require_confirm_execute and not dry_run and not confirm:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            {
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "data": _redact_sensitive_for_audit(data),
                "dry_run": dry_run,
                "confirm": confirm,
                "state": "unknown",
                "policy_decision": "denied",
                "reason": "strict_confirm_required",
            },
        )
        return {"content": [{"type": "text", "text": "Action requires confirm=true when HOME_REQUIRE_CONFIRM_EXECUTE=true."}]}
    if domain in SENSITIVE_DOMAINS and not dry_run and not confirm:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            {
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "data": _redact_sensitive_for_audit(data),
                "dry_run": dry_run,
                "confirm": confirm,
                "state": "unknown",
                "policy_decision": "denied",
                "reason": "sensitive_confirm_required",
            },
        )
        return {"content": [{"type": "text", "text": "Sensitive action requires confirm=true when dry_run=false."}]}

    current_state = "unknown"
    if not dry_run:
        if _cooldown_active(domain, action, entity_id):
            tool_feedback("done")
            record_summary("smart_home", "cooldown", start_time)
            return {"content": [{"type": "text", "text": "Action cooldown active. Try again in a moment."}]}

        state_payload, state_error = await _ha_get_state(entity_id)
        if state_error is not None:
            _record_service_error("smart_home", start_time, state_error)
            if state_error == "not_found":
                return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
            if state_error == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if state_error == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant state preflight timed out."}]}
            if state_error == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant state preflight was cancelled."}]}
            if state_error == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant for state preflight."}]}
            return {"content": [{"type": "text", "text": "Unable to validate entity state before action."}]}

        current_state = str(state_payload.get("state", "unknown")) if isinstance(state_payload, dict) else "unknown"
        if action == "turn_on" and current_state not in {"off", "unavailable", "unknown"}:
            record_summary("smart_home", "noop", start_time, effect=f"already_on {entity_id}", risk="low")
            return {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}
        if action == "turn_off" and current_state == "off":
            record_summary("smart_home", "noop", start_time, effect=f"already_off {entity_id}", risk="low")
            return {"content": [{"type": "text", "text": f"No-op: {entity_id} is already {current_state}."}]}

    _audit("smart_home", {
        "domain": domain, "action": action, "entity_id": entity_id,
        "data": _redact_sensitive_for_audit(data), "dry_run": dry_run, "confirm": confirm, "state": current_state,
        "policy_decision": "dry_run" if dry_run else "allowed",
    })

    if dry_run:
        tool_feedback("start")
        tool_feedback("done")
        record_summary(
            "smart_home",
            "dry_run",
            start_time,
            effect=f"no-op {domain}.{action} {entity_id}",
            risk="low",
        )
        return {"content": [{"type": "text", "text": (
            f"DRY RUN: Would call {domain}.{action} on {entity_id}"
            f"{' with ' + json.dumps(data, default=str) if data else ''}. "
            f"Set dry_run=false to execute."
        )}]}

    url = f"{_config.hass_url}/api/services/{domain}/{action}"
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    payload = {"entity_id": entity_id, **data}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        tool_feedback("start")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    tool_feedback("done")
                    _ha_invalidate_state(entity_id)
                    _touch_action(domain, action, entity_id)
                    record_summary(
                        "smart_home",
                        "ok",
                        start_time,
                        effect=f"executed {domain}.{action} {entity_id}",
                        risk="medium" if domain in SENSITIVE_DOMAINS else "low",
                    )
                    return {"content": [{"type": "text", "text": f"Done: {domain}.{action} on {entity_id}"}]}
                elif resp.status == 401:
                    tool_feedback("done")
                    _record_service_error("smart_home", start_time, "auth")
                    return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                elif resp.status == 404:
                    tool_feedback("done")
                    _record_service_error("smart_home", start_time, "not_found")
                    return {"content": [{"type": "text", "text": f"Service not found: {domain}.{action}"}]}
                else:
                    try:
                        text = await resp.text()
                    except Exception:
                        text = "<body unavailable>"
                    tool_feedback("done")
                    _record_service_error("smart_home", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Home Assistant error ({resp.status}): {text[:200]}"}]}
    except asyncio.TimeoutError:
        tool_feedback("done")
        _record_service_error("smart_home", start_time, "timeout")
        return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
    except asyncio.CancelledError:
        tool_feedback("done")
        _record_service_error("smart_home", start_time, "cancelled")
        return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
    except aiohttp.ClientError as e:
        tool_feedback("done")
        _record_service_error("smart_home", start_time, "network_client_error")
        return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}
    except Exception:
        tool_feedback("done")
        _record_service_error("smart_home", start_time, "unexpected")
        log.exception("Unexpected smart_home failure")
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}


async def smart_home_state(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("smart_home_state"):
        record_summary("smart_home_state", "denied", start_time, "policy")
        _audit("smart_home_state", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    from jarvis.tools.robot import tool_feedback

    if not _config or not _config.has_home_assistant:
        _record_service_error("smart_home_state", start_time, "missing_config")
        _audit("smart_home_state", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured."}]}

    entity_id = str(args.get("entity_id", "")).strip().lower()
    if not entity_id:
        _record_service_error("smart_home_state", start_time, "missing_entity")
        _audit("smart_home_state", {"result": "missing_entity"})
        return {"content": [{"type": "text", "text": "Entity id required."}]}
    tool_feedback("start")
    data, error_code = await _ha_get_state(entity_id)
    tool_feedback("done")
    if error_code is not None:
        _record_service_error("smart_home_state", start_time, error_code)
        _audit("smart_home_state", {"result": error_code, "entity_id": entity_id})
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid response from Home Assistant."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}
    payload = data or {}
    record_summary("smart_home_state", "ok", start_time)
    _audit(
        "smart_home_state",
        {
            "result": "ok",
            "entity_id": entity_id,
            "state": payload.get("state", "unknown"),
        },
    )
    return {"content": [{"type": "text", "text": json.dumps({
        "state": payload.get("state", "unknown"),
        "attributes": payload.get("attributes", {}),
    })}]}


async def todoist_add_task(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("todoist_add_task"):
        record_summary("todoist_add_task", "denied", start_time, "policy")
        _audit("todoist_add_task", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not str(_config.todoist_api_token).strip():
        _record_service_error("todoist_add_task", start_time, "missing_config")
        _audit("todoist_add_task", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Todoist not configured. Set TODOIST_API_TOKEN."}]}
    content = str(args.get("content", "")).strip()
    if not content:
        _record_service_error("todoist_add_task", start_time, "missing_fields")
        _audit("todoist_add_task", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Task content required."}]}
    payload: dict[str, Any] = {"content": content}
    description = str(args.get("description", "")).strip()
    if description:
        payload["description"] = description
    due_string = str(args.get("due_string", "")).strip()
    if due_string:
        payload["due_string"] = due_string
    priority_raw = args.get("priority", 1)
    priority = _as_exact_int(priority_raw)
    if priority is None or priority < 1 or priority > 4:
        _record_service_error("todoist_add_task", start_time, "invalid_data")
        _audit("todoist_add_task", {"result": "invalid_data", "field": "priority"})
        return {"content": [{"type": "text", "text": "Todoist priority must be an integer between 1 and 4."}]}
    payload["priority"] = priority
    labels_raw = args.get("labels")
    if labels_raw is not None:
        if not isinstance(labels_raw, list):
            _record_service_error("todoist_add_task", start_time, "invalid_data")
            _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
            return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
        labels: list[str] = []
        for item in labels_raw:
            if not isinstance(item, str):
                _record_service_error("todoist_add_task", start_time, "invalid_data")
                _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
                return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
            cleaned = item.strip()
            if not cleaned:
                _record_service_error("todoist_add_task", start_time, "invalid_data")
                _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
                return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
            labels.append(cleaned)
        if labels:
            payload["labels"] = labels
    if str(getattr(_config, "todoist_project_id", "")).strip():
        payload["project_id"] = str(_config.todoist_project_id).strip()

    headers = {
        "Authorization": f"Bearer {str(_config.todoist_api_token).strip()}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=_todoist_timeout_sec)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.todoist.com/rest/v2/tasks", headers=headers, json=payload) as resp:
                if resp.status in {200, 201}:
                    try:
                        data = await resp.json()
                    except Exception:
                        _record_service_error("todoist_add_task", start_time, "invalid_json")
                        _audit("todoist_add_task", {"result": "invalid_json"})
                        return {"content": [{"type": "text", "text": "Invalid Todoist response while creating task."}]}
                    if not isinstance(data, dict):
                        _record_service_error("todoist_add_task", start_time, "invalid_json")
                        _audit("todoist_add_task", {"result": "invalid_json"})
                        return {"content": [{"type": "text", "text": "Invalid Todoist response while creating task."}]}
                    task_id = data.get("id")
                    record_summary("todoist_add_task", "ok", start_time)
                    _audit(
                        "todoist_add_task",
                        {
                            "result": "ok",
                            "task_id": task_id,
                            "content_length": len(content),
                            "project_id": payload.get("project_id", ""),
                        },
                    )
                    return {"content": [{"type": "text", "text": f"Todoist task created{f' (id={task_id})' if task_id else ''}."}]}
                if resp.status == 401:
                    _record_service_error("todoist_add_task", start_time, "auth")
                    _audit("todoist_add_task", {"result": "auth"})
                    return {"content": [{"type": "text", "text": "Todoist authentication failed. Check TODOIST_API_TOKEN."}]}
                _record_service_error("todoist_add_task", start_time, "http_error")
                _audit("todoist_add_task", {"result": "http_error", "status": resp.status})
                return {"content": [{"type": "text", "text": f"Todoist error ({resp.status}) creating task."}]}
    except asyncio.TimeoutError:
        _record_service_error("todoist_add_task", start_time, "timeout")
        _audit("todoist_add_task", {"result": "timeout"})
        return {"content": [{"type": "text", "text": "Todoist request timed out."}]}
    except asyncio.CancelledError:
        _record_service_error("todoist_add_task", start_time, "cancelled")
        _audit("todoist_add_task", {"result": "cancelled"})
        return {"content": [{"type": "text", "text": "Todoist request was cancelled."}]}
    except aiohttp.ClientError as e:
        _record_service_error("todoist_add_task", start_time, "network_client_error")
        _audit("todoist_add_task", {"result": "network_client_error"})
        return {"content": [{"type": "text", "text": f"Failed to reach Todoist: {e}"}]}
    except Exception:
        _record_service_error("todoist_add_task", start_time, "unexpected")
        _audit("todoist_add_task", {"result": "unexpected"})
        log.exception("Unexpected todoist_add_task failure")
        return {"content": [{"type": "text", "text": "Unexpected Todoist error."}]}


async def todoist_list_tasks(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("todoist_list_tasks"):
        record_summary("todoist_list_tasks", "denied", start_time, "policy")
        _audit("todoist_list_tasks", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not str(_config.todoist_api_token).strip():
        _record_service_error("todoist_list_tasks", start_time, "missing_config")
        _audit("todoist_list_tasks", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Todoist not configured. Set TODOIST_API_TOKEN."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    list_format = str(args.get("format", "short")).strip().lower() or "short"
    if list_format not in {"short", "verbose"}:
        _record_service_error("todoist_list_tasks", start_time, "invalid_data")
        _audit("todoist_list_tasks", {"result": "invalid_data", "field": "format"})
        return {"content": [{"type": "text", "text": "Todoist list format must be 'short' or 'verbose'."}]}
    headers = {"Authorization": f"Bearer {str(_config.todoist_api_token).strip()}"}
    params: dict[str, str] = {}
    if str(getattr(_config, "todoist_project_id", "")).strip():
        params["project_id"] = str(_config.todoist_project_id).strip()
    timeout = aiohttp.ClientTimeout(total=_todoist_timeout_sec)
    attempt = 0
    while True:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params or None) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        if not isinstance(data, list):
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        if any(not isinstance(item, dict) for item in data):
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        tasks = data[:limit]
                        if not tasks:
                            record_summary("todoist_list_tasks", "empty", start_time)
                            _audit(
                                "todoist_list_tasks",
                                {
                                    "result": "empty",
                                    "limit": limit,
                                    "format": list_format,
                                    "project_id": params.get("project_id", ""),
                                },
                            )
                            return {"content": [{"type": "text", "text": "No Todoist tasks found."}]}

                        lines: list[str] = []
                        for task in tasks:
                            content = str(task.get("content", "")).strip() or "(untitled)"
                            if list_format == "short":
                                lines.append(f"- {content}")
                                continue
                            due_text = ""
                            due_payload = task.get("due")
                            if isinstance(due_payload, dict):
                                due_text = str(
                                    due_payload.get("string")
                                    or due_payload.get("date")
                                    or due_payload.get("datetime")
                                    or ""
                                ).strip()
                            labels = task.get("labels")
                            labels_text = ""
                            if isinstance(labels, list):
                                cleaned_labels = [str(item).strip() for item in labels if str(item).strip()]
                                if cleaned_labels:
                                    labels_text = ",".join(cleaned_labels)
                            meta: list[str] = []
                            if str(task.get("id", "")).strip():
                                meta.append(f"id={task['id']}")
                            if _as_exact_int(task.get("priority")) is not None:
                                meta.append(f"p={int(task['priority'])}")
                            if due_text:
                                meta.append(f"due={due_text}")
                            if labels_text:
                                meta.append(f"labels={labels_text}")
                            lines.append(f"- {content}" + (f" ({'; '.join(meta)})" if meta else ""))

                        record_summary("todoist_list_tasks", "ok", start_time)
                        _audit(
                            "todoist_list_tasks",
                            {
                                "result": "ok",
                                "count": len(tasks),
                                "limit": limit,
                                "format": list_format,
                                "project_id": params.get("project_id", ""),
                            },
                        )
                        return {"content": [{"type": "text", "text": "\n".join(lines)}]}
                    if resp.status == 401:
                        _record_service_error("todoist_list_tasks", start_time, "auth")
                        _audit("todoist_list_tasks", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Todoist authentication failed. Check TODOIST_API_TOKEN."}]}
                    _record_service_error("todoist_list_tasks", start_time, "http_error")
                    _audit("todoist_list_tasks", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Todoist error ({resp.status}) listing tasks."}]}
        except asyncio.TimeoutError:
            if attempt < TODOIST_LIST_MAX_RETRIES:
                await asyncio.sleep(_retry_backoff_delay(attempt))
                attempt += 1
                continue
            _record_service_error("todoist_list_tasks", start_time, "timeout")
            _audit("todoist_list_tasks", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Todoist request timed out."}]}
        except asyncio.CancelledError:
            _record_service_error("todoist_list_tasks", start_time, "cancelled")
            _audit("todoist_list_tasks", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Todoist request was cancelled."}]}
        except aiohttp.ClientError as e:
            if attempt < TODOIST_LIST_MAX_RETRIES:
                await asyncio.sleep(_retry_backoff_delay(attempt))
                attempt += 1
                continue
            _record_service_error("todoist_list_tasks", start_time, "network_client_error")
            _audit("todoist_list_tasks", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Todoist: {e}"}]}
        except Exception:
            _record_service_error("todoist_list_tasks", start_time, "unexpected")
            _audit("todoist_list_tasks", {"result": "unexpected"})
            log.exception("Unexpected todoist_list_tasks failure")
            return {"content": [{"type": "text", "text": "Unexpected Todoist error."}]}


async def pushover_notify(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("pushover_notify"):
        record_summary("pushover_notify", "denied", start_time, "policy")
        _audit("pushover_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not str(_config.pushover_api_token).strip() or not str(_config.pushover_user_key).strip():
        _record_service_error("pushover_notify", start_time, "missing_config")
        _audit("pushover_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("pushover_notify", start_time, "missing_fields")
        _audit("pushover_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Notification message required."}]}
    title = str(args.get("title", "Jarvis")).strip() or "Jarvis"
    priority_raw = args.get("priority", 0)
    priority = _as_exact_int(priority_raw)
    if priority is None or priority < -2 or priority > 2:
        _record_service_error("pushover_notify", start_time, "invalid_data")
        _audit("pushover_notify", {"result": "invalid_data", "field": "priority"})
        return {"content": [{"type": "text", "text": "Pushover priority must be an integer between -2 and 2."}]}
    payload = {
        "token": str(_config.pushover_api_token).strip(),
        "user": str(_config.pushover_user_key).strip(),
        "message": message,
        "title": title,
        "priority": priority,
    }
    timeout = aiohttp.ClientTimeout(total=_pushover_timeout_sec)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.pushover.net/1/messages.json", data=payload) as resp:
                if resp.status == 200:
                    try:
                        body = await resp.json()
                    except Exception:
                        _record_service_error("pushover_notify", start_time, "invalid_json")
                        _audit("pushover_notify", {"result": "invalid_json"})
                        return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                    if not isinstance(body, dict):
                        _record_service_error("pushover_notify", start_time, "invalid_json")
                        _audit("pushover_notify", {"result": "invalid_json"})
                        return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                    status_value = _as_exact_int(body.get("status"))
                    if status_value is None:
                        _record_service_error("pushover_notify", start_time, "invalid_json")
                        _audit("pushover_notify", {"result": "invalid_json"})
                        return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                    if status_value != 1:
                        errors = body.get("errors")
                        error_text = ""
                        if isinstance(errors, list):
                            error_text = "; ".join(str(item) for item in errors if str(item).strip())
                        _record_service_error("pushover_notify", start_time, "api_error")
                        _audit("pushover_notify", {"result": "api_error", "error": error_text})
                        return {"content": [{"type": "text", "text": f"Pushover rejected notification{f': {error_text}' if error_text else '.'}"}]}
                    record_summary("pushover_notify", "ok", start_time)
                    _audit(
                        "pushover_notify",
                        {
                            "result": "ok",
                            "title_length": len(title),
                            "priority": priority,
                            "message_length": len(message),
                        },
                    )
                    return {"content": [{"type": "text", "text": "Notification sent."}]}
                if resp.status in {400, 401}:
                    _record_service_error("pushover_notify", start_time, "auth")
                    _audit("pushover_notify", {"result": "auth", "status": resp.status})
                    return {"content": [{"type": "text", "text": "Pushover authentication failed."}]}
                _record_service_error("pushover_notify", start_time, "http_error")
                _audit("pushover_notify", {"result": "http_error", "status": resp.status})
                return {"content": [{"type": "text", "text": f"Pushover error ({resp.status}) sending notification."}]}
    except asyncio.TimeoutError:
        _record_service_error("pushover_notify", start_time, "timeout")
        _audit("pushover_notify", {"result": "timeout"})
        return {"content": [{"type": "text", "text": "Pushover request timed out."}]}
    except asyncio.CancelledError:
        _record_service_error("pushover_notify", start_time, "cancelled")
        _audit("pushover_notify", {"result": "cancelled"})
        return {"content": [{"type": "text", "text": "Pushover request was cancelled."}]}
    except aiohttp.ClientError as e:
        _record_service_error("pushover_notify", start_time, "network_client_error")
        _audit("pushover_notify", {"result": "network_client_error"})
        return {"content": [{"type": "text", "text": f"Failed to reach Pushover: {e}"}]}
    except Exception:
        _record_service_error("pushover_notify", start_time, "unexpected")
        _audit("pushover_notify", {"result": "unexpected"})
        log.exception("Unexpected pushover_notify failure")
        return {"content": [{"type": "text", "text": "Unexpected Pushover error."}]}


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

    recent_tools: list[dict[str, object]] | dict[str, str]
    try:
        recent_tools = list_summaries(limit=5)
    except Exception as e:
        recent_tools = {"error": str(e)}
    health = _health_rollup(
        config_present=(_config is not None),
        memory_status=memory_status if isinstance(memory_status, dict) else None,
        recent_tools=recent_tools,
    )

    status = {
        "local_time": _now_local(),
        "home_assistant_configured": bool(_config and _config.has_home_assistant),
        "todoist_configured": bool(_config and str(_config.todoist_api_token).strip()),
        "pushover_configured": bool(
            _config
            and str(_config.pushover_api_token).strip()
            and str(_config.pushover_user_key).strip()
        ),
        "motion_enabled": bool(_config and _config.motion_enabled),
        "home_tools_enabled": bool(_config and _config.home_enabled),
        "memory_enabled": bool(_config and _config.memory_enabled),
        "backchannel_style": _config.backchannel_style if _config else "unknown",
        "persona_style": _config.persona_style if _config else "unknown",
        "tool_policy": {
            "allow_count": len(_tool_allowlist),
            "deny_count": len(_tool_denylist),
            "home_permission_profile": _home_permission_profile,
            "home_require_confirm_execute": bool(_home_require_confirm_execute),
            "todoist_permission_profile": _todoist_permission_profile,
            "notification_permission_profile": _notification_permission_profile,
        },
        "memory": memory_status,
        "audit": _audit_status(),
        "recent_tools": recent_tools,
        "health": health,
    }
    record_summary("system_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status, default=str)}]}


# ── Memory + planning ───────────────────────────────────────

async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_add"):
        record_summary("memory_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_add", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    tags_raw = args.get("tags")
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    kind = str(args.get("kind", "note"))
    importance = _as_float(args.get("importance", 0.5), 0.5, minimum=0.0, maximum=1.0)
    sensitivity = _as_float(args.get("sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    source = str(args.get("source", "user"))
    try:
        memory_id = _memory.add_memory(
            text,
            kind=kind,
            tags=tags,
            importance=importance,
            sensitivity=sensitivity,
            source=source,
        )
    except Exception as e:
        _record_service_error("memory_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory add failed: {e}"}]}
    record_summary("memory_add", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Memory stored (id={memory_id})."}]}


async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_search"):
        record_summary("memory_search", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_search", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    query = str(args.get("query", "")).strip()
    if not query:
        _record_service_error("memory_search", start_time, "missing_query")
        return {"content": [{"type": "text", "text": "Search query required."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    default_max_sensitivity = _as_float(
        getattr(_config, "memory_max_sensitivity", 0.4),
        0.4,
        minimum=0.0,
        maximum=1.0,
    )
    default_hybrid_weight = _as_float(
        getattr(_config, "memory_hybrid_weight", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    default_decay_enabled = _as_bool(getattr(_config, "memory_decay_enabled", False), default=False)
    default_decay_half_life_days = _as_float(
        getattr(_config, "memory_decay_half_life_days", 30.0),
        30.0,
        minimum=0.1,
    )
    default_mmr_enabled = _as_bool(getattr(_config, "memory_mmr_enabled", False), default=False)
    default_mmr_lambda = _as_float(
        getattr(_config, "memory_mmr_lambda", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    include_sensitive = _as_bool(args.get("include_sensitive"), default=False)
    max_sensitivity = None if include_sensitive else _as_float(
        args.get("max_sensitivity", default_max_sensitivity),
        default_max_sensitivity,
        minimum=0.0,
        maximum=1.0,
    )
    source_list = _as_str_list(args.get("sources"))
    try:
        results = _memory.search_v2(
            query,
            limit=limit,
            max_sensitivity=max_sensitivity,
            hybrid_weight=_as_float(
                args.get("hybrid_weight", default_hybrid_weight),
                default_hybrid_weight,
                minimum=0.0,
                maximum=1.0,
            ),
            decay_enabled=_as_bool(args.get("decay_enabled"), default=default_decay_enabled),
            decay_half_life_days=_as_float(
                args.get("decay_half_life_days", default_decay_half_life_days),
                default_decay_half_life_days,
                minimum=0.1,
            ),
            mmr_enabled=_as_bool(args.get("mmr_enabled"), default=default_mmr_enabled),
            mmr_lambda=_as_float(
                args.get("mmr_lambda", default_mmr_lambda),
                default_mmr_lambda,
                minimum=0.0,
                maximum=1.0,
            ),
            sources=source_list,
        )
    except Exception as e:
        _record_service_error("memory_search", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory search failed: {e}"}]}
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
        _record_service_error("memory_status", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    try:
        if _as_bool(args.get("warm"), default=False):
            _memory.warm()
        if _as_bool(args.get("sync"), default=False):
            _memory.sync()
        if _as_bool(args.get("optimize"), default=False):
            _memory.optimize()
        if _as_bool(args.get("vacuum"), default=False):
            _memory.vacuum()
        status = _memory.memory_status()
    except Exception as e:
        _record_service_error("memory_status", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory status failed: {e}"}]}
    record_summary("memory_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status)}]}


async def memory_recent(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_recent"):
        record_summary("memory_recent", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_recent", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    kind = args.get("kind")
    source_list = _as_str_list(args.get("sources"))
    try:
        results = _memory.recent(limit=limit, kind=str(kind) if kind else None, sources=source_list)
    except Exception as e:
        _record_service_error("memory_recent", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory recent failed: {e}"}]}
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
        _record_service_error("memory_summary_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    topic = str(args.get("topic", "")).strip()
    summary = str(args.get("summary", "")).strip()
    if not topic or not summary:
        _record_service_error("memory_summary_add", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Summary topic and text required."}]}
    try:
        _memory.upsert_summary(topic, summary)
    except Exception as e:
        _record_service_error("memory_summary_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary add failed: {e}"}]}
    record_summary("memory_summary_add", "ok", start_time)
    return {"content": [{"type": "text", "text": "Summary stored."}]}


async def memory_summary_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_list"):
        record_summary("memory_summary_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    try:
        results = _memory.list_summaries(limit=limit)
    except Exception as e:
        _record_service_error("memory_summary_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary list failed: {e}"}]}
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
        _record_service_error("task_plan_create", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    title = str(args.get("title", "")).strip()
    steps = args.get("steps")
    if not title or not isinstance(steps, list) or not steps:
        _record_service_error("task_plan_create", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan title and steps required."}]}
    try:
        plan_id = _memory.add_task_plan(title, [str(step) for step in steps])
    except ValueError:
        _record_service_error("task_plan_create", start_time, "invalid_steps")
        return {"content": [{"type": "text", "text": "Plan requires at least one non-empty step."}]}
    except Exception as e:
        _record_service_error("task_plan_create", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan create failed: {e}"}]}
    record_summary("task_plan_create", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Plan created (id={plan_id})."}]}


async def task_plan_list(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("task_plan_list"):
        record_summary("task_plan_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("task_plan_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    open_only = _as_bool(args.get("open_only"), default=True)
    try:
        plans = _memory.list_task_plans(open_only=open_only)
    except Exception as e:
        _record_service_error("task_plan_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan list failed: {e}"}]}
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
        _record_service_error("task_plan_update", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_exact_int(args.get("plan_id"))
    step_index = _as_exact_int(args.get("step_index"))
    status = str(args.get("status", "pending")).strip().lower()
    allowed_status = {"pending", "in_progress", "blocked", "done"}
    if plan_id is None or plan_id <= 0 or step_index is None or step_index < 0:
        _record_service_error("task_plan_update", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Plan id and step index required."}]}
    if status not in allowed_status:
        _record_service_error("task_plan_update", start_time, "invalid_status")
        return {"content": [{"type": "text", "text": "Status must be one of: pending, in_progress, blocked, done."}]}
    try:
        updated = _memory.update_task_step(plan_id, step_index, status)
    except Exception as e:
        _record_service_error("task_plan_update", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan update failed: {e}"}]}
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
        _record_service_error("task_plan_summary", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = _as_exact_int(args.get("plan_id"))
    if plan_id is None or plan_id <= 0:
        _record_service_error("task_plan_summary", start_time, "missing_plan")
        return {"content": [{"type": "text", "text": "Plan id required."}]}
    try:
        progress = _memory.task_plan_progress(plan_id)
    except Exception as e:
        _record_service_error("task_plan_summary", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan summary failed: {e}"}]}
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
        _record_service_error("task_plan_next", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    plan_id = args.get("plan_id")
    parsed_plan_id = _as_exact_int(plan_id) if plan_id is not None else None
    if plan_id is not None and (parsed_plan_id is None or parsed_plan_id <= 0):
        _record_service_error("task_plan_next", start_time, "invalid_plan")
        return {"content": [{"type": "text", "text": "Plan id must be a positive integer."}]}
    try:
        plan = _memory.next_task_step(parsed_plan_id) if parsed_plan_id else _memory.next_task_step()
    except Exception as e:
        _record_service_error("task_plan_next", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Task plan next failed: {e}"}]}
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
    try:
        summaries = list_summaries(limit)
    except Exception as e:
        _record_service_error("tool_summary", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(summaries, default=str)}]}


async def tool_summary_text(args: dict[str, Any]) -> dict[str, Any]:
    start_time = time.monotonic()
    if not _tool_permitted("tool_summary_text"):
        record_summary("tool_summary_text", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 6), 6, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
        text = _format_tool_summaries(summaries)
    except Exception as e:
        _record_service_error("tool_summary_text", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary_text", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}


# ── Build MCP server ──────────────────────────────────────────

smart_home_tool = tool(
    "smart_home",
    "Control smart home devices via Home Assistant. "
    "For destructive actions (unlock doors, disable alarms, open covers), set dry_run=true first. "
    "Always explain what you're about to do before executing.",
    SERVICE_TOOL_SCHEMAS["smart_home"],
)(smart_home)


smart_home_state_tool = tool(
    "smart_home_state",
    "Get the current state of a Home Assistant entity.",
    SERVICE_TOOL_SCHEMAS["smart_home_state"],
)(smart_home_state)

todoist_add_task_tool = tool(
    "todoist_add_task",
    "Create a task in Todoist (project configurable via env).",
    SERVICE_TOOL_SCHEMAS["todoist_add_task"],
)(todoist_add_task)

todoist_list_tasks_tool = tool(
    "todoist_list_tasks",
    "List active tasks from Todoist.",
    SERVICE_TOOL_SCHEMAS["todoist_list_tasks"],
)(todoist_list_tasks)

pushover_notify_tool = tool(
    "pushover_notify",
    "Send a push notification via Pushover.",
    SERVICE_TOOL_SCHEMAS["pushover_notify"],
)(pushover_notify)


get_time_tool = tool(
    "get_time",
    "Get the current local time (device clock).",
    SERVICE_TOOL_SCHEMAS["get_time"],
)(get_time)

system_status_tool = tool(
    "system_status",
    "Report current runtime capabilities and health snapshot.",
    SERVICE_TOOL_SCHEMAS["system_status"],
)(system_status)

memory_add_tool = tool(
    "memory_add",
    "Store a long-term memory (facts, preferences, summaries).",
    SERVICE_TOOL_SCHEMAS["memory_add"],
)(memory_add)

memory_search_tool = tool(
    "memory_search",
    "Search long-term memory for relevant entries.",
    SERVICE_TOOL_SCHEMAS["memory_search"],
)(memory_search)

memory_status_tool = tool(
    "memory_status",
    "Report memory index status and availability.",
    SERVICE_TOOL_SCHEMAS["memory_status"],
)(memory_status)

memory_recent_tool = tool(
    "memory_recent",
    "List recent memory entries.",
    SERVICE_TOOL_SCHEMAS["memory_recent"],
)(memory_recent)

memory_summary_add_tool = tool(
    "memory_summary_add",
    "Store or update a short memory summary for a topic.",
    SERVICE_TOOL_SCHEMAS["memory_summary_add"],
)(memory_summary_add)

memory_summary_list_tool = tool(
    "memory_summary_list",
    "List recent memory summaries.",
    SERVICE_TOOL_SCHEMAS["memory_summary_list"],
)(memory_summary_list)

task_plan_create_tool = tool(
    "task_plan_create",
    "Create a multi-step task plan and store it.",
    SERVICE_TOOL_SCHEMAS["task_plan_create"],
)(task_plan_create)

task_plan_list_tool = tool(
    "task_plan_list",
    "List stored task plans (optionally open only).",
    SERVICE_TOOL_SCHEMAS["task_plan_list"],
)(task_plan_list)

task_plan_update_tool = tool(
    "task_plan_update",
    "Update a task plan step status.",
    SERVICE_TOOL_SCHEMAS["task_plan_update"],
)(task_plan_update)

task_plan_summary_tool = tool(
    "task_plan_summary",
    "Summarize progress for a task plan.",
    SERVICE_TOOL_SCHEMAS["task_plan_summary"],
)(task_plan_summary)

task_plan_next_tool = tool(
    "task_plan_next",
    "Get the next pending step in a task plan.",
    SERVICE_TOOL_SCHEMAS["task_plan_next"],
)(task_plan_next)

tool_summary_tool = tool(
    "tool_summary",
    "Return recent tool execution summaries (latency/outcome).",
    SERVICE_TOOL_SCHEMAS["tool_summary"],
)(tool_summary)

tool_summary_text_tool = tool(
    "tool_summary_text",
    "Summarize recent tool executions for the user.",
    SERVICE_TOOL_SCHEMAS["tool_summary_text"],
)(tool_summary_text)

def create_services_server():
    return create_sdk_mcp_server(
        name="jarvis-services",
        version="0.1.0",
        tools=[
            smart_home_tool,
            smart_home_state_tool,
            todoist_add_task_tool,
            todoist_list_tasks_tool,
            pushover_notify_tool,
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
