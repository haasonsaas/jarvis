"""Status action for home automation drafts/applied state."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_orch_automation_status(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _slugify_identifier = s._slugify_identifier
    _home_automation_drafts = s._home_automation_drafts
    _home_automation_applied = s._home_automation_applied
    _automation_entry_from_draft = s._automation_entry_from_draft

    draft_id = str(args.get("draft_id", "")).strip()
    automation_id = _slugify_identifier(str(args.get("automation_id", "")).strip(), fallback="")
    if draft_id:
        row = _home_automation_drafts.get(draft_id)
        payload = {"action": "automation_status", "draft_id": draft_id, "draft": _automation_entry_from_draft(row or {})}
    elif automation_id:
        row = _home_automation_applied.get(automation_id, {})
        payload = {
            "action": "automation_status",
            "automation_id": automation_id,
            "applied": {
                "automation_id": automation_id,
                "has_current": bool(isinstance(row, dict) and isinstance(row.get("current"), dict) and row.get("current")),
                "history_count": len(row.get("history", [])) if isinstance(row, dict) and isinstance(row.get("history"), list) else 0,
                "updated_at": float(row.get("updated_at", 0.0) or 0.0) if isinstance(row, dict) else 0.0,
            },
        }
    else:
        payload = {
            "action": "automation_status",
            "draft_count": len(_home_automation_drafts),
            "applied_count": len(_home_automation_applied),
            "drafts": [
                _automation_entry_from_draft(row)
                for row in sorted(_home_automation_drafts.values(), key=lambda item: str(item.get("draft_id", "")))[:100]
            ],
            "applied_ids": sorted(_home_automation_applied.keys())[:100],
        }
    record_summary("home_orchestrator", "ok", start_time, effect="automation_status", risk="low")
    return _expansion_payload_response(payload)
