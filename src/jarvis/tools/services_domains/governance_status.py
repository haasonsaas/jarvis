"""System status and scorecard handlers for governance domain."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_governance_runtime import (
    scorecard_context as _runtime_scorecard_context,
    system_status_contract_payload as _runtime_system_status_contract_payload,
    system_status_payload as _runtime_system_status_payload,
)


def _services():
    from jarvis.tools import services as s

    return s

async def system_status(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _jarvis_scorecard_snapshot = s._jarvis_scorecard_snapshot
    SYSTEM_STATUS_CONTRACT_VERSION = s.SYSTEM_STATUS_CONTRACT_VERSION
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("system_status"):
        record_summary("system_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    expansion_status = s._expansion_snapshot()
    context = _runtime_scorecard_context(s, recent_tool_limit=5)
    scorecard = _jarvis_scorecard_snapshot(
        recent_tools=context["recent_tools"],
        health=context["health"],
        observability=context["observability_status"],
        identity=context["identity_status"],
        tool_policy=context["tool_policy_status"],
        audit=context["audit_status"],
        integrations=context["integrations_status"],
    )
    status = _runtime_system_status_payload(
        s,
        schema_version=SYSTEM_STATUS_CONTRACT_VERSION,
        scorecard=scorecard,
        expansion_status=expansion_status,
        context=context,
    )
    record_summary("system_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status, default=str)}]}


async def system_status_contract(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    SYSTEM_STATUS_CONTRACT_VERSION = s.SYSTEM_STATUS_CONTRACT_VERSION
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("system_status_contract"):
        record_summary("system_status_contract", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    contract = _runtime_system_status_contract_payload(
        schema_version=SYSTEM_STATUS_CONTRACT_VERSION
    )
    record_summary("system_status_contract", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(contract)}]}


async def jarvis_scorecard(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _jarvis_scorecard_snapshot = s._jarvis_scorecard_snapshot
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("jarvis_scorecard"):
        record_summary("jarvis_scorecard", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    context = _runtime_scorecard_context(s, recent_tool_limit=200)
    recent_tools = context["recent_tools"]
    identity_status = context["identity_status"]
    tool_policy_status = context["tool_policy_status"]
    observability_status = context["observability_status"]
    integrations_status = context["integrations_status"]
    audit_status = context["audit_status"]
    health = context["health"]
    scorecard = _jarvis_scorecard_snapshot(
        recent_tools=recent_tools,
        health=health,
        observability=observability_status,
        identity=identity_status,
        tool_policy=tool_policy_status,
        audit=audit_status,
        integrations=integrations_status,
    )
    record_summary("jarvis_scorecard", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(scorecard, default=str)}]}
