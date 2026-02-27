"""Home orchestration handlers."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def home_orchestrator(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _home_plan_from_request = s._home_plan_from_request
    _home_area_policy_violation = s._home_area_policy_violation
    _home_area_policies = s._home_area_policies
    _home_task_runs = s._home_task_runs
    _as_float = s._as_float
    _as_int = s._as_int
    _as_bool = s._as_bool
    _as_str_list = s._as_str_list
    _normalize_automation_config = s._normalize_automation_config
    _slugify_identifier = s._slugify_identifier
    _home_automation_drafts = s._home_automation_drafts
    _home_automation_applied = s._home_automation_applied
    _automation_entry_from_draft = s._automation_entry_from_draft
    _json_preview = s._json_preview
    _structured_diff = s._structured_diff
    _apply_ha_automation_config = s._apply_ha_automation_config
    _delete_ha_automation_config = s._delete_ha_automation_config
    _autonomy_tasks = s._autonomy_tasks
    HOME_AUTOMATION_MAX_TRACKED = s.HOME_AUTOMATION_MAX_TRACKED
    HOME_TASK_MAX_TRACKED = s.HOME_TASK_MAX_TRACKED

    start_time = time.monotonic()
    if not _tool_permitted("home_orchestrator"):
        record_summary("home_orchestrator", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "plan":
        request_text = str(args.get("request_text", "")).strip()
        plan = _home_plan_from_request(request_text)
        payload = {
            "action": action,
            "request_text": request_text,
            "plan_label": plan["label"],
            "step_count": len(plan["steps"]),
            "steps": plan["steps"],
        }
        record_summary("home_orchestrator", "ok", start_time, effect=f"plan:{plan['label']}", risk="low")
        return _expansion_payload_response(payload)

    if action == "execute":
        actions = args.get("actions") if isinstance(args.get("actions"), list) else []
        results: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for row in actions:
            if not isinstance(row, dict):
                results.append({"status": "failed", "reason": "invalid_action_entry"})
                continue
            domain = str(row.get("domain", "")).strip().lower()
            tool_action = str(row.get("action", "")).strip().lower()
            entity_id = str(row.get("entity_id", "")).strip().lower()
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            if not domain or not tool_action or not entity_id:
                results.append({"status": "failed", "reason": "missing_fields", "entry": row})
                continue
            pair = f"{domain}:{tool_action}:{entity_id}"
            if pair in seen_keys:
                results.append({"status": "failed", "reason": "duplicate_action", "entry": row})
                continue
            seen_keys.add(pair)
            blocked, reason = _home_area_policy_violation(
                domain=domain,
                action=tool_action,
                entity_id=entity_id,
                data=data,
            )
            if blocked:
                results.append({"status": "failed", "reason": "area_policy", "detail": reason, "entry": row})
                continue
            results.append({"status": "ok", "entry": row, "preflight": "passed"})
        ok_count = sum(1 for item in results if item.get("status") == "ok")
        fail_count = len(results) - ok_count
        payload = {
            "action": action,
            "executed_count": ok_count,
            "failed_count": fail_count,
            "partial_failure": ok_count > 0 and fail_count > 0,
            "results": results,
        }
        record_summary("home_orchestrator", "ok", start_time, effect=f"execute_ok={ok_count}_fail={fail_count}", risk="medium" if fail_count else "low")
        return _expansion_payload_response(payload)

    if action == "area_policy_set":
        area = str(args.get("area", "")).strip().lower()
        policy = args.get("policy") if isinstance(args.get("policy"), dict) else {}
        if not area:
            _record_service_error("home_orchestrator", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "area is required for area_policy_set."}]}
        _home_area_policies[area] = {
            "blocked_actions": sorted(set(_as_str_list(policy.get("blocked_actions"), lower=True))),
            "quiet_hours_start": str(policy.get("quiet_hours_start", "")).strip(),
            "quiet_hours_end": str(policy.get("quiet_hours_end", "")).strip(),
            "updated_at": time.time(),
        }
        payload = {"action": action, "area": area, "policy": dict(_home_area_policies[area]), "policy_count": len(_home_area_policies)}
        record_summary("home_orchestrator", "ok", start_time, effect="area_policy_set", risk="low")
        return _expansion_payload_response(payload)

    if action == "area_policy_list":
        area = str(args.get("area", "")).strip().lower()
        if area:
            payload = {"action": action, "area": area, "policy": dict(_home_area_policies.get(area, {}))}
        else:
            payload = {"action": action, "policy_count": len(_home_area_policies), "policies": {name: dict(row) for name, row in sorted(_home_area_policies.items())}}
        record_summary("home_orchestrator", "ok", start_time, effect="area_policy_list", risk="low")
        return _expansion_payload_response(payload)

    if action == "automation_suggest":
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
        payload = {"action": action, "suggestion_count": len(suggestions), "suggestions": suggestions}
        record_summary("home_orchestrator", "ok", start_time, effect=f"automation_suggestions={len(suggestions)}", risk="low")
        return _expansion_payload_response(payload)

    if action == "automation_create":
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
            "action": action,
            "draft": _automation_entry_from_draft(draft),
            "config_preview": _json_preview(config_payload),
            "draft_count": len(_home_automation_drafts),
        }
        record_summary("home_orchestrator", "ok", start_time, effect="automation_create", risk="low")
        return _expansion_payload_response(payload)

    if action == "automation_apply":
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
                "action": action,
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
            "action": action,
            "dry_run": False,
            "applied": True,
            "ha_status": ha_status,
            "draft": _automation_entry_from_draft(draft),
            "diff": diff,
        }
        record_summary("home_orchestrator", "ok", start_time, effect="automation_apply", risk="medium")
        return _expansion_payload_response(payload)

    if action == "automation_rollback":
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
                "action": action,
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
            "action": action,
            "dry_run": False,
            "rolled_back": True,
            "ha_status": ha_status,
            "automation_id": automation_id,
            "restored_revision": bool(previous),
            "diff": diff,
        }
        record_summary("home_orchestrator", "ok", start_time, effect="automation_rollback", risk="medium")
        return _expansion_payload_response(payload)

    if action == "automation_status":
        draft_id = str(args.get("draft_id", "")).strip()
        automation_id = _slugify_identifier(str(args.get("automation_id", "")).strip(), fallback="")
        if draft_id:
            row = _home_automation_drafts.get(draft_id)
            payload = {"action": action, "draft_id": draft_id, "draft": _automation_entry_from_draft(row or {})}
        elif automation_id:
            row = _home_automation_applied.get(automation_id, {})
            payload = {
                "action": action,
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
                "action": action,
                "draft_count": len(_home_automation_drafts),
                "applied_count": len(_home_automation_applied),
                "drafts": [_automation_entry_from_draft(row) for row in sorted(_home_automation_drafts.values(), key=lambda item: str(item.get("draft_id", "")))[:100]],
                "applied_ids": sorted(_home_automation_applied.keys())[:100],
            }
        record_summary("home_orchestrator", "ok", start_time, effect="automation_status", risk="low")
        return _expansion_payload_response(payload)

    if action == "task_start":
        task_id = f"home-task-{s._home_task_seq}"
        s._home_task_seq += 1
        row = {
            "task_id": task_id,
            "status": "in_progress",
            "progress": _as_float(args.get("progress", 0.0), 0.0, minimum=0.0, maximum=1.0),
            "notes": str(args.get("notes", "")).strip(),
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        _home_task_runs[task_id] = row
        if len(_home_task_runs) > HOME_TASK_MAX_TRACKED:
            oldest = sorted(_home_task_runs.items(), key=lambda pair: float(pair[1].get("updated_at", 0.0)))[: len(_home_task_runs) - HOME_TASK_MAX_TRACKED]
            for key, _ in oldest:
                _home_task_runs.pop(key, None)
        record_summary("home_orchestrator", "ok", start_time, effect="task_start", risk="low")
        return _expansion_payload_response({"action": action, "task": row, "task_count": len(_home_task_runs)})

    if action == "task_update":
        task_id = str(args.get("task_id", "")).strip()
        row = _home_task_runs.get(task_id)
        if row is None:
            _record_service_error("home_orchestrator", start_time, "not_found")
            return {"content": [{"type": "text", "text": "task_id not found."}]}
        status = str(args.get("status", row.get("status", "in_progress"))).strip().lower() or "in_progress"
        if status not in {"queued", "in_progress", "completed", "failed", "cancelled"}:
            _record_service_error("home_orchestrator", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "status must be queued|in_progress|completed|failed|cancelled."}]}
        row["status"] = status
        row["progress"] = _as_float(args.get("progress", row.get("progress", 0.0)), float(row.get("progress", 0.0)), minimum=0.0, maximum=1.0)
        row["notes"] = str(args.get("notes", row.get("notes", ""))).strip()
        row["updated_at"] = time.time()
        record_summary("home_orchestrator", "ok", start_time, effect="task_update", risk="low")
        return _expansion_payload_response({"action": action, "task": dict(row)})

    if action == "task_list":
        limit = _as_int(args.get("limit", 50), 50, minimum=1, maximum=200)
        tasks = sorted(_home_task_runs.values(), key=lambda row: float(row.get("updated_at", 0.0)), reverse=True)[:limit]
        record_summary("home_orchestrator", "ok", start_time, effect="task_list", risk="low")
        return _expansion_payload_response({"action": action, "task_count": len(_home_task_runs), "tasks": tasks})

    _record_service_error("home_orchestrator", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown home_orchestrator action."}]}


