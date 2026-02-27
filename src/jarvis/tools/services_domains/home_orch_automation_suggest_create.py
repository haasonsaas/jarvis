"""Automation suggestion/create handlers for home orchestrator."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_orch_automation_suggest(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response

    history = args.get("history") if isinstance(args.get("history"), list) else []
    counts: dict[str, int] = {}
    for row in history:
        if not isinstance(row, dict):
            continue
        domain = str(row.get("domain", "")).strip().lower()
        tool_action = str(row.get("action", "")).strip().lower()
        entity = str(row.get("entity_id", "")).strip().lower()
        if not domain or not tool_action or not entity:
            continue
        key = f"{domain}:{tool_action}:{entity}"
        counts[key] = counts.get(key, 0) + 1
    suggestions = [
        {
            "trigger": "time",
            "description": f"Frequent action {key} ({count}x)",
            "ha_automation_yaml": (
                "alias: Jarvis Suggested Routine\n"
                "trigger:\n  - platform: time\n    at: '21:00:00'\n"
                "action:\n"
                f"  - service: {key.split(':', 1)[0]}.{key.split(':', 2)[1]}\n"
                f"    target:\n      entity_id: {key.split(':', 2)[2]}"
            ),
        }
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 3
    ][:5]
    payload = {"action": "automation_suggest", "suggestion_count": len(suggestions), "suggestions": suggestions}
    record_summary("home_orchestrator", "ok", start_time, effect=f"automation_suggestions={len(suggestions)}", risk="low")
    return _expansion_payload_response(payload)


async def home_orch_automation_create(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _normalize_automation_config = s._normalize_automation_config
    _slugify_identifier = s._slugify_identifier
    _home_automation_drafts = s._home_automation_drafts
    _automation_entry_from_draft = s._automation_entry_from_draft
    _json_preview = s._json_preview
    HOME_AUTOMATION_MAX_TRACKED = s.HOME_AUTOMATION_MAX_TRACKED

    config_payload, error = _normalize_automation_config(args)
    if config_payload is None:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": error}]}
    draft_id = f"automation-draft-{s._home_automation_seq}"
    s._home_automation_seq += 1
    automation_id = _slugify_identifier(
        str(args.get("automation_id", "")).strip() or config_payload.get("alias", "automation"),
        fallback="automation",
    )
    now = time.time()
    draft = {
        "draft_id": draft_id,
        "automation_id": automation_id,
        "alias": str(config_payload.get("alias", "")),
        "config": config_payload,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    _home_automation_drafts[draft_id] = draft
    if len(_home_automation_drafts) > HOME_AUTOMATION_MAX_TRACKED:
        oldest = sorted(
            _home_automation_drafts.items(),
            key=lambda pair: float(pair[1].get("updated_at", 0.0)),
        )[: len(_home_automation_drafts) - HOME_AUTOMATION_MAX_TRACKED]
        for key, _ in oldest:
            _home_automation_drafts.pop(key, None)
    payload = {
        "action": "automation_create",
        "draft": _automation_entry_from_draft(draft),
        "config_preview": _json_preview(config_payload),
        "draft_count": len(_home_automation_drafts),
    }
    record_summary("home_orchestrator", "ok", start_time, effect="automation_create", risk="low")
    return _expansion_payload_response(payload)
