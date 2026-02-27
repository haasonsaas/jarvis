"""Automation apply/rollback/status handlers for home orchestrator."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_orch_automation_apply(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _as_bool = s._as_bool
    _home_automation_drafts = s._home_automation_drafts
    _home_automation_applied = s._home_automation_applied
    _automation_entry_from_draft = s._automation_entry_from_draft
    _structured_diff = s._structured_diff
    _apply_ha_automation_config = s._apply_ha_automation_config

    draft_id = str(args.get("draft_id", "")).strip()
    draft = _home_automation_drafts.get(draft_id)
    if not isinstance(draft, dict):
        _record_service_error("home_orchestrator", start_time, "not_found")
        return {"content": [{"type": "text", "text": "draft_id not found."}]}
    automation_id = str(draft.get("automation_id", "")).strip()
    dry_run = _as_bool(args.get("dry_run"), default=True)
    confirm = _as_bool(args.get("confirm"), default=False)
    ha_apply = _as_bool(args.get("ha_apply"), default=True)
    applied_row = _home_automation_applied.get(automation_id, {})
    previous = applied_row.get("current") if isinstance(applied_row, dict) and isinstance(applied_row.get("current"), dict) else {}
    current = draft.get("config") if isinstance(draft.get("config"), dict) else {}
    diff = _structured_diff(previous if isinstance(previous, dict) else {}, current if isinstance(current, dict) else {})
    if dry_run:
        payload = {
            "action": "automation_apply",
            "dry_run": True,
            "draft": _automation_entry_from_draft(draft),
            "diff": diff,
            "ha_apply": bool(ha_apply),
        }
        record_summary("home_orchestrator", "ok", start_time, effect="automation_apply_preview", risk="low")
        return _expansion_payload_response(payload)
    if not confirm:
        _record_service_error("home_orchestrator", start_time, "confirm_required")
        return {"content": [{"type": "text", "text": "automation_apply requires confirm=true when dry_run=false."}]}
    ha_status = "skipped"
    if ha_apply:
        ok, error_code = await _apply_ha_automation_config(automation_id, current if isinstance(current, dict) else {})
        if not ok:
            _record_service_error("home_orchestrator", start_time, error_code or "unexpected")
            return {"content": [{"type": "text", "text": f"Home Assistant automation apply failed: {error_code or 'unexpected'}."}]}
        ha_status = "applied"
    row = _home_automation_applied.setdefault(automation_id, {"history": []})
    history = row.get("history")
    if not isinstance(history, list):
        history = []
    existing_current = row.get("current")
    if isinstance(existing_current, dict) and existing_current:
        history.append(
            {
                "config": existing_current,
                "saved_at": float(row.get("updated_at", time.time()) or time.time()),
                "source_draft_id": str(row.get("last_draft_id", "")),
            }
        )
    if len(history) > 20:
        history = history[-20:]
    row["history"] = history
    row["current"] = current
    row["updated_at"] = time.time()
    row["last_draft_id"] = draft_id
    draft["status"] = "applied"
    draft["updated_at"] = time.time()
    payload = {
        "action": "automation_apply",
        "dry_run": False,
        "applied": True,
        "ha_status": ha_status,
        "draft": _automation_entry_from_draft(draft),
        "diff": diff,
    }
    record_summary("home_orchestrator", "ok", start_time, effect="automation_apply", risk="medium")
    return _expansion_payload_response(payload)


async def home_orch_automation_rollback(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _as_bool = s._as_bool
    _slugify_identifier = s._slugify_identifier
    _home_automation_applied = s._home_automation_applied
    _structured_diff = s._structured_diff
    _apply_ha_automation_config = s._apply_ha_automation_config
    _delete_ha_automation_config = s._delete_ha_automation_config

    automation_id = _slugify_identifier(str(args.get("automation_id", "")).strip(), fallback="")
    if not automation_id:
        _record_service_error("home_orchestrator", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "automation_id is required for automation_rollback."}]}
    row = _home_automation_applied.get(automation_id)
    if not isinstance(row, dict):
        _record_service_error("home_orchestrator", start_time, "not_found")
        return {"content": [{"type": "text", "text": "automation_id has no applied state."}]}
    current = row.get("current") if isinstance(row.get("current"), dict) else {}
    history = row.get("history") if isinstance(row.get("history"), list) else []
    previous_entry = history[-1] if history else {}
    previous = previous_entry.get("config") if isinstance(previous_entry, dict) and isinstance(previous_entry.get("config"), dict) else {}
    dry_run = _as_bool(args.get("dry_run"), default=True)
    confirm = _as_bool(args.get("confirm"), default=False)
    ha_apply = _as_bool(args.get("ha_apply"), default=True)
    diff = _structured_diff(current if isinstance(current, dict) else {}, previous if isinstance(previous, dict) else {})
    if dry_run:
        payload = {
            "action": "automation_rollback",
            "dry_run": True,
            "automation_id": automation_id,
            "has_previous_revision": bool(previous),
            "diff": diff,
            "ha_apply": bool(ha_apply),
        }
        record_summary("home_orchestrator", "ok", start_time, effect="automation_rollback_preview", risk="low")
        return _expansion_payload_response(payload)
    if not confirm:
        _record_service_error("home_orchestrator", start_time, "confirm_required")
        return {"content": [{"type": "text", "text": "automation_rollback requires confirm=true when dry_run=false."}]}
    ha_status = "skipped"
    if ha_apply:
        if isinstance(previous, dict) and previous:
            ok, error_code = await _apply_ha_automation_config(automation_id, previous)
        else:
            ok, error_code = await _delete_ha_automation_config(automation_id)
        if not ok:
            _record_service_error("home_orchestrator", start_time, error_code or "unexpected")
            return {"content": [{"type": "text", "text": f"Home Assistant automation rollback failed: {error_code or 'unexpected'}."}]}
        ha_status = "rolled_back"
    if history:
        history.pop()
    if isinstance(previous, dict) and previous:
        row["current"] = previous
        row["history"] = history
        row["updated_at"] = time.time()
    else:
        _home_automation_applied.pop(automation_id, None)
    payload = {
        "action": "automation_rollback",
        "dry_run": False,
        "rolled_back": True,
        "ha_status": ha_status,
        "automation_id": automation_id,
        "restored_revision": bool(previous),
        "diff": diff,
    }
    record_summary("home_orchestrator", "ok", start_time, effect="automation_rollback", risk="medium")
    return _expansion_payload_response(payload)


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
