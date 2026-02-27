"""Skill registry lifecycle handlers."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def skills_list(args: dict[str, Any]) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    suppress = s.suppress
    set_runtime_skills_state = s.set_runtime_skills_state
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("skills_list"):
        record_summary("skills_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    with suppress(Exception):
        _skill_registry.discover()
        set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(_skill_registry.status_snapshot(), default=str)}]}


async def skills_enable(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    set_runtime_skills_state = s.set_runtime_skills_state
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("skills_enable"):
        record_summary("skills_enable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_enable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_enable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.enable_skill(name)
    if not ok:
        _record_service_error("skills_enable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to enable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_enable", "ok", start_time)
    _audit("skills_enable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Enabled skill '{name}'."}]}


async def skills_disable(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    set_runtime_skills_state = s.set_runtime_skills_state
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("skills_disable"):
        record_summary("skills_disable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_disable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_disable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.disable_skill(name)
    if not ok:
        _record_service_error("skills_disable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to disable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_disable", "ok", start_time)
    _audit("skills_disable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Disabled skill '{name}'."}]}


async def skills_version(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("skills_version"):
        record_summary("skills_version", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_version", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_version", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    version = _skill_registry.skill_version(name)
    if version is None:
        _record_service_error("skills_version", start_time, "not_found")
        return {"content": [{"type": "text", "text": f"Skill '{name}' not found."}]}
    record_summary("skills_version", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps({"name": name, "version": version})}]}
