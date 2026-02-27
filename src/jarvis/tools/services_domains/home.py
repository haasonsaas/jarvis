"""Home domain service handlers extracted from services.py."""

from __future__ import annotations

import json
import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def smart_home_state(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _ha_get_state = s._ha_get_state

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
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
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
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "state": payload.get("state", "unknown"),
                        "attributes": payload.get("attributes", {}),
                    }
                ),
            }
        ]
    }


async def home_assistant_capabilities(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    _tool_permitted = s._tool_permitted
    record_summary = s.record_summary
    _audit = s._audit
    _record_service_error = s._record_service_error
    _config = s._config
    _as_bool = s._as_bool
    _ha_get_state = s._ha_get_state
    _ha_get_domain_services = s._ha_get_domain_services

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_capabilities"):
        record_summary("home_assistant_capabilities", "denied", start_time, "policy")
        _audit("home_assistant_capabilities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_capabilities", start_time, "missing_config")
        _audit("home_assistant_capabilities", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    entity_id = str(args.get("entity_id", "")).strip().lower()
    if not entity_id:
        _record_service_error("home_assistant_capabilities", start_time, "missing_entity")
        _audit("home_assistant_capabilities", {"result": "missing_entity"})
        return {"content": [{"type": "text", "text": "Entity id required."}]}
    include_services = _as_bool(args.get("include_services"), default=True)

    state_payload, state_error = await _ha_get_state(entity_id)
    if state_error is not None:
        _record_service_error("home_assistant_capabilities", start_time, state_error)
        _audit("home_assistant_capabilities", {"result": state_error, "entity_id": entity_id})
        if state_error == "not_found":
            return {"content": [{"type": "text", "text": f"Entity not found: {entity_id}"}]}
        if state_error == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if state_error == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid response from Home Assistant."}]}
        if state_error == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        if state_error == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        if state_error == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if state_error == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}

    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    services_for_domain: list[str] = []
    if include_services and domain:
        service_names, service_error = await _ha_get_domain_services(domain)
        if service_error is not None:
            _record_service_error("home_assistant_capabilities", start_time, service_error)
            _audit(
                "home_assistant_capabilities",
                {
                    "result": service_error,
                    "entity_id": entity_id,
                    "domain": domain,
                    "phase": "service_catalog",
                },
            )
            if service_error == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed while reading services."}]}
            if service_error == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant service catalog response."}]}
            if service_error == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant service catalog request timed out."}]}
            if service_error == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant service catalog request was cancelled."}]}
            if service_error == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if service_error == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant service catalog endpoint."}]}
            return {"content": [{"type": "text", "text": "Unable to fetch Home Assistant service catalog."}]}
        services_for_domain = service_names or []

    payload = state_payload or {}
    result = {
        "entity_id": entity_id,
        "domain": domain,
        "state": payload.get("state", "unknown"),
        "attributes": payload.get("attributes", {}),
        "available_services": services_for_domain,
    }
    record_summary("home_assistant_capabilities", "ok", start_time)
    _audit(
        "home_assistant_capabilities",
        {
            "result": "ok",
            "entity_id": entity_id,
            "domain": domain,
            "include_services": include_services,
            "service_count": len(services_for_domain),
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


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


async def smart_home(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    asyncio = s.asyncio
    json = s.json
    aiohttp = s.aiohttp
    log = s.log
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    HA_MUTATING_ALLOWED_ACTIONS = s.HA_MUTATING_ALLOWED_ACTIONS
    _ha_action_allowed = s._ha_action_allowed
    _as_bool = s._as_bool
    SENSITIVE_DOMAINS = s.SENSITIVE_DOMAINS
    _safe_mode_enabled = s._safe_mode_enabled
    _identity_authorize = s._identity_authorize
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _redact_sensitive_for_audit = s._redact_sensitive_for_audit
    _home_require_confirm_execute = s._home_require_confirm_execute
    _is_ambiguous_entity_target = s._is_ambiguous_entity_target
    _home_area_policy_violation = s._home_area_policy_violation
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack
    _cooldown_active = s._cooldown_active
    _ha_get_state = s._ha_get_state
    _ha_headers = s._ha_headers
    _effective_act_timeout = s._effective_act_timeout
    _recovery_operation = s._recovery_operation
    _ha_invalidate_state = s._ha_invalidate_state
    _touch_action = s._touch_action
    _integration_record_success = s._integration_record_success

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
    dry_run = _as_bool(args.get("dry_run"), default=domain in SENSITIVE_DOMAINS)
    confirm = _as_bool(args.get("confirm"), default=False)
    safe_mode_forced = _safe_mode_enabled and not dry_run
    if safe_mode_forced:
        dry_run = True
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "smart_home",
        args,
        mutating=not dry_run,
        high_risk=(not dry_run and domain in SENSITIVE_DOMAINS),
    )
    if not identity_allowed:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "data": _redact_sensitive_for_audit(data),
                    "dry_run": dry_run,
                    "confirm": confirm,
                    "safe_mode_forced": safe_mode_forced,
                    "state": "unknown",
                    "policy_decision": "denied",
                    "reason": "identity_policy",
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_require_confirm_execute and not dry_run and not confirm:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "data": _redact_sensitive_for_audit(data),
                    "dry_run": dry_run,
                    "confirm": confirm,
                    "safe_mode_forced": safe_mode_forced,
                    "state": "unknown",
                    "policy_decision": "denied",
                    "reason": "strict_confirm_required",
                },
                identity_context,
                [*identity_chain, "deny:strict_confirm_required"],
            ),
        )
        return {"content": [{"type": "text", "text": "Action requires confirm=true when HOME_REQUIRE_CONFIRM_EXECUTE=true."}]}
    if domain in SENSITIVE_DOMAINS and not dry_run and not confirm:
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "data": _redact_sensitive_for_audit(data),
                    "dry_run": dry_run,
                    "confirm": confirm,
                    "safe_mode_forced": safe_mode_forced,
                    "state": "unknown",
                    "policy_decision": "denied",
                    "reason": "sensitive_confirm_required",
                },
                identity_context,
                [*identity_chain, "deny:sensitive_confirm_required"],
            ),
        )
        return {"content": [{"type": "text", "text": "Sensitive action requires confirm=true when dry_run=false."}]}
    if domain in SENSITIVE_DOMAINS and not dry_run and _is_ambiguous_entity_target(entity_id):
        _record_service_error("smart_home", start_time, "policy")
        _audit(
            "smart_home",
            _identity_enriched_audit(
                {
                    "domain": domain,
                    "action": action,
                    "entity_id": entity_id,
                    "policy_decision": "denied",
                    "reason": "ambiguous_target",
                },
                identity_context,
                [*identity_chain, "deny:ambiguous_target"],
            ),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Ambiguous high-risk target. Specify one explicit entity instead of a broad/group target.",
                }
            ]
        }
    if not dry_run:
        area_blocked, area_reason = _home_area_policy_violation(
            domain=domain,
            action=action,
            entity_id=entity_id,
            data=data,
        )
        if area_blocked:
            _record_service_error("smart_home", start_time, "policy")
            _audit(
                "smart_home",
                _identity_enriched_audit(
                    {
                        "domain": domain,
                        "action": action,
                        "entity_id": entity_id,
                        "policy_decision": "denied",
                        "reason": "area_policy",
                        "detail": area_reason,
                    },
                    identity_context,
                    [*identity_chain, "deny:area_policy"],
                ),
            )
            return {"content": [{"type": "text", "text": area_reason}]}
    if not dry_run:
        preview_risk = "high" if domain in SENSITIVE_DOMAINS else "medium"
        preview = _preview_gate(
            tool_name="smart_home",
            args=args,
            risk=preview_risk,
            summary=f"{domain}.{action} on {entity_id}",
            signature_payload={
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "data": _redact_sensitive_for_audit(data),
            },
            enforce_default=s._plan_preview_require_ack,
        )
        if preview:
            record_summary("smart_home", "dry_run", start_time, effect="plan_preview", risk=preview_risk)
            _audit(
                "smart_home",
                _identity_enriched_audit(
                    {
                        "domain": domain,
                        "action": action,
                        "entity_id": entity_id,
                        "policy_decision": "preview_required",
                    },
                    identity_context,
                    [*identity_chain, "decision:preview_required"],
                ),
            )
            return {"content": [{"type": "text", "text": preview}]}

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
            if state_error == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
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

    _audit(
        "smart_home",
        _identity_enriched_audit(
            {
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "data": _redact_sensitive_for_audit(data),
                "dry_run": dry_run,
                "confirm": confirm,
                "safe_mode_forced": safe_mode_forced,
                "state": current_state,
                "policy_decision": "dry_run" if dry_run else "allowed",
            },
            identity_context,
            [*identity_chain, "decision:dry_run" if dry_run else "decision:execute"],
        ),
    )

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
            f"{'Safe mode forced dry-run. ' if safe_mode_forced else ''}"
            f"Set dry_run=false to execute."
        )}]}

    url = f"{_config.hass_url}/api/services/{domain}/{action}"
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    payload = {"entity_id": entity_id, **data}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(10.0))
    with _recovery_operation(
        "smart_home",
        operation=f"{domain}.{action}",
        context={"entity_id": entity_id, "domain": domain},
    ) as recovery:
        try:
            tool_feedback("start")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        tool_feedback("done")
                        _ha_invalidate_state(entity_id)
                        _touch_action(domain, action, entity_id)
                        _integration_record_success("home_assistant")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary(
                            "smart_home",
                            "ok",
                            start_time,
                            effect=f"executed {domain}.{action} {entity_id}",
                            risk="medium" if domain in SENSITIVE_DOMAINS else "low",
                        )
                        return {"content": [{"type": "text", "text": f"Done: {domain}.{action} on {entity_id}"}]}
                    if resp.status == 401:
                        tool_feedback("done")
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("smart_home", start_time, "auth")
                        return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                    if resp.status == 404:
                        tool_feedback("done")
                        recovery.mark_failed("not_found", context={"http_status": resp.status})
                        _record_service_error("smart_home", start_time, "not_found")
                        return {"content": [{"type": "text", "text": f"Service not found: {domain}.{action}"}]}
                    try:
                        text = await resp.text()
                    except Exception:
                        text = "<body unavailable>"
                    tool_feedback("done")
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("smart_home", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Home Assistant error ({resp.status}): {text[:200]}"}]}
        except asyncio.TimeoutError:
            tool_feedback("done")
            recovery.mark_failed("timeout")
            _record_service_error("smart_home", start_time, "timeout")
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        except asyncio.CancelledError:
            tool_feedback("done")
            recovery.mark_cancelled()
            _record_service_error("smart_home", start_time, "cancelled")
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        except aiohttp.ClientError as e:
            tool_feedback("done")
            recovery.mark_failed("network_client_error")
            _record_service_error("smart_home", start_time, "network_client_error")
            return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}
        except Exception:
            tool_feedback("done")
            recovery.mark_failed("unexpected")
            _record_service_error("smart_home", start_time, "unexpected")
            log.exception("Unexpected smart_home failure")
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}


async def home_assistant_conversation(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    _audit = s._audit
    _integration_circuit_open = s._integration_circuit_open
    _integration_circuit_open_message = s._integration_circuit_open_message
    _home_conversation_enabled = s._home_conversation_enabled
    _home_conversation_permission_profile = s._home_conversation_permission_profile
    HA_CONVERSATION_MAX_TEXT_CHARS = s.HA_CONVERSATION_MAX_TEXT_CHARS
    _is_ambiguous_high_risk_text = s._is_ambiguous_high_risk_text
    _as_bool = s._as_bool
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack
    _effective_act_timeout = s._effective_act_timeout
    _ha_headers = s._ha_headers
    _recovery_operation = s._recovery_operation
    _ha_conversation_speech = s._ha_conversation_speech
    _integration_record_success = s._integration_record_success

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_conversation"):
        record_summary("home_assistant_conversation", "denied", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_conversation", start_time, "missing_config")
        _audit("home_assistant_conversation", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("home_assistant")
    if circuit_open:
        _record_service_error("home_assistant_conversation", start_time, "circuit_open")
        _audit("home_assistant_conversation", {"result": "circuit_open"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": _integration_circuit_open_message("home_assistant", circuit_remaining),
                }
            ]
        }
    if not _home_conversation_enabled:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "conversation_disabled"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant conversation tool is disabled. Set HOME_CONVERSATION_ENABLED=true to enable.",
                }
            ]
        }
    if _home_conversation_permission_profile != "control":
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "conversation_readonly_profile"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant conversation requires HOME_CONVERSATION_PERMISSION_PROFILE=control.",
                }
            ]
        }
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("home_assistant_conversation", start_time, "missing_fields")
        _audit("home_assistant_conversation", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Conversation text is required."}]}
    if len(text) > HA_CONVERSATION_MAX_TEXT_CHARS:
        _record_service_error("home_assistant_conversation", start_time, "invalid_data")
        _audit("home_assistant_conversation", {"result": "invalid_data", "field": "text_length", "length": len(text)})
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Conversation text exceeds {HA_CONVERSATION_MAX_TEXT_CHARS} characters.",
                }
            ]
        }
    if _is_ambiguous_high_risk_text(text):
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "ambiguous_high_risk_text"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "That risky command is ambiguous. Name the exact target entity/device before execution.",
                }
            ]
        }
    confirm = _as_bool(args.get("confirm"), default=False)
    if not confirm:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "confirm_required", "text_length": len(text)})
        return {"content": [{"type": "text", "text": "Set confirm=true to execute a Home Assistant conversation command."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_conversation",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit(
            "home_assistant_conversation",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "text_length": len(text)},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    preview = _preview_gate(
        tool_name="home_assistant_conversation",
        args=args,
        risk="high",
        summary=f"conversation command: {text[:120]}",
        signature_payload={
            "text": text,
            "language": str(args.get("language", "")).strip(),
            "agent_id": str(args.get("agent_id", "")).strip(),
        },
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("home_assistant_conversation", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "home_assistant_conversation",
            _identity_enriched_audit(
                {"result": "preview_required", "text_length": len(text)},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}

    payload: dict[str, Any] = {"text": text}
    language = str(args.get("language", "")).strip()
    if language:
        payload["language"] = language
    agent_id = str(args.get("agent_id", "")).strip()
    if agent_id:
        payload["agent_id"] = agent_id
    url = f"{_config.hass_url}/api/conversation/process"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(10.0))
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    with _recovery_operation(
        "home_assistant_conversation",
        operation="conversation_process",
        context={"text_length": len(text)},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        try:
                            body = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("home_assistant_conversation", start_time, "invalid_json")
                            _audit("home_assistant_conversation", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Home Assistant conversation response."}]}
                        if not isinstance(body, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("home_assistant_conversation", start_time, "invalid_json")
                            _audit("home_assistant_conversation", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Home Assistant conversation response."}]}
                        response_type = ""
                        response = body.get("response")
                        if isinstance(response, dict):
                            response_type = str(response.get("response_type", "")).strip()
                        speech = _ha_conversation_speech(body)
                        if not speech:
                            speech = "Home Assistant processed the command."
                        conversation_id = str(body.get("conversation_id", "")).strip()
                        _integration_record_success("home_assistant")
                        recovery.mark_completed(
                            detail="ok",
                            context={
                                "response_type": response_type,
                                "conversation_id": conversation_id,
                            },
                        )
                        record_summary("home_assistant_conversation", "ok", start_time)
                        _audit(
                            "home_assistant_conversation",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "response_type": response_type,
                                    "conversation_id": conversation_id,
                                    "text_length": len(text),
                                    "language": language,
                                    "agent_id": agent_id,
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        suffix = ""
                        if response_type:
                            suffix += f" [type={response_type}]"
                        if conversation_id:
                            suffix += f" [conversation_id={conversation_id}]"
                        return {"content": [{"type": "text", "text": f"{speech}{suffix}"}]}
                    if resp.status == 401:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("home_assistant_conversation", start_time, "auth")
                        _audit("home_assistant_conversation", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                    if resp.status == 404:
                        recovery.mark_failed("not_found", context={"http_status": resp.status})
                        _record_service_error("home_assistant_conversation", start_time, "not_found")
                        _audit("home_assistant_conversation", {"result": "not_found"})
                        return {"content": [{"type": "text", "text": "Home Assistant conversation endpoint not found."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("home_assistant_conversation", start_time, "http_error")
                    _audit("home_assistant_conversation", {"result": "http_error", "status": resp.status})
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Home Assistant conversation error ({resp.status}).",
                            }
                        ]
                    }
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("home_assistant_conversation", start_time, "timeout")
            _audit("home_assistant_conversation", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Home Assistant conversation request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("home_assistant_conversation", start_time, "cancelled")
            _audit("home_assistant_conversation", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Home Assistant conversation request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("home_assistant_conversation", start_time, "network_client_error")
            _audit("home_assistant_conversation", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant conversation endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("home_assistant_conversation", start_time, "unexpected")
            _audit("home_assistant_conversation", {"result": "unexpected"})
            log.exception("Unexpected home_assistant_conversation failure")
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant conversation error."}]}


async def home_assistant_todo(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile
    _ha_call_service = s._ha_call_service
    _collect_json_lists_by_key = s._collect_json_lists_by_key
    _recovery_operation = s._recovery_operation

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_todo"):
        record_summary("home_assistant_todo", "denied", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_todo", start_time, "missing_config")
        _audit("home_assistant_todo", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"list", "add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "invalid_data")
        _audit("home_assistant_todo", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: list, add, remove."}]}
    if not entity_id:
        _record_service_error("home_assistant_todo", start_time, "missing_fields")
        _audit("home_assistant_todo", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_todo",
        args,
        mutating=(action in {"add", "remove"}),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit(
            "home_assistant_todo",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action in {"add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "list":
        payload, error_code = await _ha_call_service(
            "todo",
            "get_items",
            {
                "entity_id": entity_id,
                **(
                    {"status": str(args.get("status", "")).strip()}
                    if str(args.get("status", "")).strip()
                    else {}
                ),
            },
            return_response=True,
        )
        if error_code is not None:
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"To-do entity or service not found: {entity_id}"}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        items = [item for item in _collect_json_lists_by_key(payload, "items") if isinstance(item, dict)]
        if not items:
            record_summary("home_assistant_todo", "empty", start_time)
            _audit("home_assistant_todo", {"result": "empty", "action": action, "entity_id": entity_id})
            return {"content": [{"type": "text", "text": "No Home Assistant to-do items found."}]}
        lines: list[str] = []
        for item in items:
            summary = str(item.get("summary") or item.get("item") or "").strip() or "(untitled)"
            uid = str(item.get("uid") or item.get("id") or "").strip()
            status = str(item.get("status", "")).strip()
            due = str(item.get("due") or item.get("due_datetime") or "").strip()
            meta: list[str] = []
            if uid:
                meta.append(f"id={uid}")
            if status:
                meta.append(f"status={status}")
            if due:
                meta.append(f"due={due}")
            lines.append(f"- {summary}" + (f" ({'; '.join(meta)})" if meta else ""))
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {"result": "ok", "action": action, "entity_id": entity_id, "count": len(lines)},
        )
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    item = str(args.get("item", "")).strip()
    item_id = str(args.get("item_id", "")).strip()
    if action == "add":
        if not item:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item is required when action=add."}]}
        service = "add_item"
        service_data = {"entity_id": entity_id, "item": item}
        success_text = "Added Home Assistant to-do item."
    else:
        if not item and not item_id:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item or item_id is required when action=remove."}]}
        service = "remove_item"
        service_data = {"entity_id": entity_id, "item": item_id or item}
        success_text = "Removed Home Assistant to-do item."

    with _recovery_operation(
        "home_assistant_todo",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("todo", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant to-do entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {
                "result": "ok",
                "action": action,
                "entity_id": entity_id,
                "item_length": len(item),
                "item_id": item_id,
            },
        )
        return {"content": [{"type": "text", "text": success_text}]}


async def home_assistant_timer(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    re = s.re
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile
    _ha_get_state = s._ha_get_state
    _duration_seconds = s._duration_seconds
    _recovery_operation = s._recovery_operation
    _ha_call_service = s._ha_call_service

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_timer"):
        record_summary("home_assistant_timer", "denied", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_timer", start_time, "missing_config")
        _audit("home_assistant_timer", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"state", "start", "pause", "cancel", "finish"}:
        _record_service_error("home_assistant_timer", start_time, "invalid_data")
        _audit("home_assistant_timer", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: state, start, pause, cancel, finish."}]}
    if not entity_id:
        _record_service_error("home_assistant_timer", start_time, "missing_fields")
        _audit("home_assistant_timer", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_timer",
        args,
        mutating=(action != "state"),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit(
            "home_assistant_timer",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action != "state":
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "state":
        payload, error_code = await _ha_get_state(entity_id)
        if error_code is not None:
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"Timer not found: {entity_id}"}]}
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        body = payload or {}
        attributes = body.get("attributes", {}) if isinstance(body, dict) else {}
        result = {
            "entity_id": entity_id,
            "state": body.get("state", "unknown") if isinstance(body, dict) else "unknown",
            "remaining": attributes.get("remaining") if isinstance(attributes, dict) else None,
            "duration": attributes.get("duration") if isinstance(attributes, dict) else None,
            "finishes_at": attributes.get("finishes_at") if isinstance(attributes, dict) else None,
        }
        record_summary("home_assistant_timer", "ok", start_time)
        _audit("home_assistant_timer", {"result": "ok", "action": action, "entity_id": entity_id})
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    service_map = {
        "start": "start",
        "pause": "pause",
        "cancel": "cancel",
        "finish": "finish",
    }
    service_data: dict[str, Any] = {"entity_id": entity_id}
    if action == "start":
        duration_text = str(args.get("duration", "")).strip()
        if duration_text:
            duration_seconds = _duration_seconds(duration_text)
            if duration_seconds is not None:
                total = max(1, int(round(duration_seconds)))
                hours, rem = divmod(total, 3600)
                minutes, seconds = divmod(rem, 60)
                service_data["duration"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            elif re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", duration_text):
                service_data["duration"] = duration_text
            else:
                _record_service_error("home_assistant_timer", start_time, "invalid_data")
                _audit("home_assistant_timer", {"result": "invalid_data", "field": "duration"})
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "duration must be HH:MM:SS or a relative duration like 5m.",
                        }
                    ]
                }
    with _recovery_operation(
        "home_assistant_timer",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("timer", service_map[action], service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant timer entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        recovery.mark_completed(detail="ok", context={"duration": service_data.get("duration")})
        record_summary("home_assistant_timer", "ok", start_time)
        _audit(
            "home_assistant_timer",
            {"result": "ok", "action": action, "entity_id": entity_id, "duration": service_data.get("duration")},
        )
        return {"content": [{"type": "text", "text": f"Home Assistant timer action executed: {action} on {entity_id}."}]}


async def home_assistant_area_entities(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _ha_render_template = s._ha_render_template
    _ha_get_state = s._ha_get_state

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_area_entities"):
        record_summary("home_assistant_area_entities", "denied", start_time, "policy")
        _audit("home_assistant_area_entities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_area_entities", start_time, "missing_config")
        _audit("home_assistant_area_entities", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    area = str(args.get("area", "")).strip()
    if not area:
        _record_service_error("home_assistant_area_entities", start_time, "missing_fields")
        _audit("home_assistant_area_entities", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "area is required."}]}
    domain_filter = str(args.get("domain", "")).strip().lower()
    include_states = _as_bool(args.get("include_states"), default=False)

    template = f"{{{{ area_entities({json.dumps(area)}) | join('\\n') }}}}"
    rendered, error_code = await _ha_render_template(template)
    if error_code is not None:
        _record_service_error("home_assistant_area_entities", start_time, error_code)
        _audit("home_assistant_area_entities", {"result": error_code, "area": area})
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Home Assistant template endpoint not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup was cancelled."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant area lookup endpoint."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant area lookup error."}]}

    raw_entities = [line.strip().lower() for line in (rendered or "").splitlines() if line.strip()]
    entities = sorted(set(raw_entities))
    if domain_filter:
        entities = [entity for entity in entities if entity.startswith(f"{domain_filter}.")]
    if not entities:
        record_summary("home_assistant_area_entities", "empty", start_time)
        _audit(
            "home_assistant_area_entities",
            {"result": "empty", "area": area, "domain": domain_filter},
        )
        return {"content": [{"type": "text", "text": "No entities found for that area filter."}]}

    payload: dict[str, Any] = {"area": area, "domain": domain_filter or None, "entities": entities}
    if include_states:
        states: list[dict[str, Any]] = []
        for entity_id in entities[:100]:
            entity_state, state_error = await _ha_get_state(entity_id)
            if state_error is not None:
                continue
            state_payload = entity_state or {}
            attributes = state_payload.get("attributes")
            friendly_name = ""
            if isinstance(attributes, dict):
                friendly_name = str(attributes.get("friendly_name", "")).strip()
            states.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "state": state_payload.get("state", "unknown"),
                }
            )
        payload["states"] = states
    record_summary("home_assistant_area_entities", "ok", start_time)
    _audit(
        "home_assistant_area_entities",
        {
            "result": "ok",
            "area": area,
            "domain": domain_filter,
            "count": len(entities),
            "include_states": include_states,
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


async def media_control(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    math = s.math
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _as_bool = s._as_bool
    _safe_mode_enabled = s._safe_mode_enabled
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_area_policy_violation = s._home_area_policy_violation
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack
    _recovery_operation = s._recovery_operation
    _ha_call_service = s._ha_call_service

    start_time = time.monotonic()
    if not _tool_permitted("media_control"):
        record_summary("media_control", "denied", start_time, "policy")
        _audit("media_control", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("media_control", start_time, "missing_config")
        _audit("media_control", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    entity_id = str(args.get("entity_id", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()
    if not entity_id.startswith("media_player."):
        _record_service_error("media_control", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "entity_id must be a media_player entity."}]}
    action_map = {
        "play": ("media_play", {}),
        "pause": ("media_pause", {}),
        "turn_on": ("turn_on", {}),
        "turn_off": ("turn_off", {}),
        "toggle": ("toggle", {}),
        "mute": ("volume_mute", {"is_volume_muted": True}),
        "unmute": ("volume_mute", {"is_volume_muted": False}),
        "volume_set": ("volume_set", {}),
    }
    if action not in action_map:
        _record_service_error("media_control", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "action must be one of: play, pause, turn_on, turn_off, toggle, mute, unmute, volume_set.",
                }
            ]
        }
    service, data = action_map[action]
    payload_data = dict(data)
    if action == "volume_set":
        volume = _as_float(args.get("volume"), float("nan"))
        if not math.isfinite(volume) or volume < 0.0 or volume > 1.0:
            _record_service_error("media_control", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "volume must be a number between 0.0 and 1.0 for volume_set."}]}
        payload_data["volume_level"] = volume
    dry_run = _as_bool(args.get("dry_run"), default=False)
    safe_mode_forced = _safe_mode_enabled and not dry_run
    if safe_mode_forced:
        dry_run = True
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "media_control",
        args,
        mutating=not dry_run,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("media_control", start_time, "policy")
        _audit(
            "media_control",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "entity_id": entity_id, "action": action},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if not dry_run:
        area_blocked, area_reason = _home_area_policy_violation(
            domain="media_player",
            action=service,
            entity_id=entity_id,
            data=payload_data,
        )
        if area_blocked:
            _record_service_error("media_control", start_time, "policy")
            _audit(
                "media_control",
                _identity_enriched_audit(
                    {
                        "result": "denied",
                        "reason": "area_policy",
                        "entity_id": entity_id,
                        "action": action,
                        "detail": area_reason,
                    },
                    identity_context,
                    [*identity_chain, "deny:area_policy"],
                ),
            )
            return {"content": [{"type": "text", "text": area_reason}]}
    if not dry_run:
        preview = _preview_gate(
            tool_name="media_control",
            args=args,
            risk="medium",
            summary=f"media_control {action} on {entity_id}",
            signature_payload={"entity_id": entity_id, "action": action, "payload_data": payload_data},
            enforce_default=s._plan_preview_require_ack,
        )
        if preview:
            record_summary("media_control", "dry_run", start_time, effect="plan_preview", risk="medium")
            _audit(
                "media_control",
                _identity_enriched_audit(
                    {"result": "preview_required", "entity_id": entity_id, "action": action},
                    identity_context,
                    [*identity_chain, "decision:preview_required"],
                ),
            )
            return {"content": [{"type": "text", "text": preview}]}
    if dry_run:
        record_summary("media_control", "dry_run", start_time)
        _audit(
            "media_control",
            _identity_enriched_audit(
                {
                    "result": "dry_run",
                    "entity_id": entity_id,
                    "action": action,
                    "data": payload_data,
                    "safe_mode_forced": safe_mode_forced,
                },
                identity_context,
                [*identity_chain, "decision:dry_run"],
            ),
        )
        text = f"DRY RUN: media_player.{service} on {entity_id} with {payload_data}"
        if safe_mode_forced:
            text = f"{text}. Safe mode forced dry-run."
        return {"content": [{"type": "text", "text": text}]}
    service_data = {"entity_id": entity_id, **payload_data}
    with _recovery_operation(
        "media_control",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("media_player", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("media_control", start_time, error_code)
            _audit("media_control", {"result": error_code, "entity_id": entity_id, "action": action})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Media player entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Media control request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Media control request was cancelled."}]}
            if error_code == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant media endpoint."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant media control error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("media_control", "ok", start_time, effect=f"{service} {entity_id}", risk="low")
        _audit(
            "media_control",
            _identity_enriched_audit(
                {"result": "ok", "entity_id": entity_id, "action": action},
                identity_context,
                [*identity_chain, "decision:execute"],
            ),
        )
        return {"content": [{"type": "text", "text": f"Media action executed: {action} on {entity_id}."}]}
