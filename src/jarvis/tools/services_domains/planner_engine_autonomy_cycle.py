"""Autonomy cycle handler for planner engine."""

from __future__ import annotations

import asyncio
import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _resolve_path(data: Any, path: str) -> tuple[Any, bool]:
    current = data
    for segment in [item for item in path.split(".") if item]:
        if isinstance(current, dict):
            if segment not in current:
                return None, False
            current = current.get(segment)
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                return None, False
            index = int(segment)
            if index < 0 or index >= len(current):
                return None, False
            current = current[index]
            continue
        return None, False
    return current, True


def _normalize_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _safe_condition_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def _evaluate_condition(
    condition: dict[str, Any] | None,
    *,
    row: dict[str, Any],
    runtime_state: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    if not isinstance(condition, dict) or not condition:
        return True, {"applied": False, "reason_code": "condition_not_set"}
    source = str(condition.get("source", "runtime")).strip().lower() or "runtime"
    if source not in {"runtime", "payload", "task"}:
        source = "runtime"
    path = str(condition.get("path", "")).strip().strip(".")
    if not path:
        return False, {"applied": True, "source": source, "path": "", "reason_code": "condition_path_missing"}
    roots: dict[str, Any] = {
        "runtime": runtime_state,
        "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
        "task": row,
    }
    actual_value, exists = _resolve_path(roots.get(source), path)
    evidence: dict[str, Any] = {
        "applied": True,
        "source": source,
        "path": path,
        "exists": exists,
        "actual": _safe_condition_value(actual_value),
    }
    if "exists" in condition:
        expected_exists = bool(condition.get("exists"))
        evidence["expected_exists"] = expected_exists
        if exists != expected_exists:
            evidence["reason_code"] = "condition_exists_mismatch"
            return False, evidence
    if "equals" in condition:
        expected_value = condition.get("equals")
        evidence["expected_equals"] = _safe_condition_value(expected_value)
        if actual_value != expected_value:
            evidence["reason_code"] = "condition_equals_mismatch"
            return False, evidence
    if isinstance(condition.get("in"), list):
        expected_values = list(condition.get("in", []))
        evidence["expected_in"] = [_safe_condition_value(item) for item in expected_values]
        if actual_value not in expected_values:
            evidence["reason_code"] = "condition_not_in_allowed_set"
            return False, evidence
    if "gte" in condition:
        actual_num = _normalize_number(actual_value)
        expected_gte = _normalize_number(condition.get("gte"))
        evidence["expected_gte"] = expected_gte
        if actual_num is None or expected_gte is None:
            evidence["reason_code"] = "condition_gte_non_numeric"
            return False, evidence
        if actual_num < expected_gte:
            evidence["reason_code"] = "condition_gte_unmet"
            return False, evidence
    if "lte" in condition:
        actual_num = _normalize_number(actual_value)
        expected_lte = _normalize_number(condition.get("lte"))
        evidence["expected_lte"] = expected_lte
        if actual_num is None or expected_lte is None:
            evidence["reason_code"] = "condition_lte_non_numeric"
            return False, evidence
        if actual_num > expected_lte:
            evidence["reason_code"] = "condition_lte_unmet"
            return False, evidence
    evidence["reason_code"] = "condition_met"
    return True, evidence


def _record_failure_taxonomy(row: dict[str, Any], reason_code: str) -> None:
    taxonomy = row.get("failure_taxonomy")
    if not isinstance(taxonomy, dict):
        taxonomy = {}
        row["failure_taxonomy"] = taxonomy
    key = str(reason_code or "unknown_failure").strip().lower() or "unknown_failure"
    taxonomy[key] = int(taxonomy.get(key, 0) or 0) + 1


def _coerce_attempt_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    mapped: dict[str, int] = {}
    for key, raw in value.items():
        step_key = str(key).strip()
        if not step_key:
            continue
        try:
            attempt = int(raw)
        except (TypeError, ValueError):
            attempt = 0
        mapped[step_key] = max(0, min(100, attempt))
    return mapped


def _deep_merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {str(key): value for key, value in base.items()}
    for key, value in overlay.items():
        key_text = str(key)
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key_text), dict)
        ):
            merged[key_text] = _deep_merge_dicts(
                merged[key_text],
                value,
            )
            continue
        merged[key_text] = value
    return merged


def _entity_id_from_runtime_path(path: str) -> str:
    segments = [item for item in str(path).strip().strip(".").split(".") if item]
    if len(segments) < 4:
        return ""
    if segments[0] not in {"home_assistant", "ha"}:
        return ""
    if segments[1] != "entities":
        return ""
    domain = str(segments[2]).strip().lower()
    object_id = str(segments[3]).strip().lower()
    if not domain or not object_id:
        return ""
    return f"{domain}.{object_id}"


def _collect_contract_entity_ids(
    rows: list[dict[str, Any]],
) -> list[str]:
    entity_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        step_contracts = row.get("step_contracts")
        if not isinstance(step_contracts, list):
            continue
        for contract in step_contracts:
            if not isinstance(contract, dict):
                continue
            for phase in ("precondition", "postcondition"):
                condition = contract.get(phase)
                if not isinstance(condition, dict):
                    continue
                source = str(condition.get("source", "runtime")).strip().lower() or "runtime"
                if source != "runtime":
                    continue
                entity_id = _entity_id_from_runtime_path(condition.get("path", ""))
                if entity_id:
                    entity_ids.add(entity_id)
    return sorted(entity_ids)


def _nested_home_assistant_entity_slot(
    payload: dict[str, Any],
    entity_id: str,
) -> dict[str, Any]:
    parts = [item for item in entity_id.split(".") if item]
    if len(parts) != 2:
        return {}
    domain, object_id = parts
    home_assistant = payload.setdefault("home_assistant", {})
    if not isinstance(home_assistant, dict):
        home_assistant = {}
        payload["home_assistant"] = home_assistant
    entities = home_assistant.setdefault("entities", {})
    if not isinstance(entities, dict):
        entities = {}
        home_assistant["entities"] = entities
    domain_group = entities.setdefault(domain, {})
    if not isinstance(domain_group, dict):
        domain_group = {}
        entities[domain] = domain_group
    slot = domain_group.setdefault(object_id, {})
    if not isinstance(slot, dict):
        slot = {}
        domain_group[object_id] = slot
    return slot


async def _runtime_state_snapshot(
    *,
    user_runtime_state: dict[str, Any],
    due_rows: list[dict[str, Any]],
    explicit_ha_entities: list[str],
) -> dict[str, Any]:
    s = _services()
    runtime_payload: dict[str, Any] = {
        "runtime": {
            "voice": (
                {str(key): value for key, value in s._runtime_voice_state.items()}
                if isinstance(s._runtime_voice_state, dict)
                else {}
            ),
            "observability": (
                {str(key): value for key, value in s._runtime_observability_state.items()}
                if isinstance(s._runtime_observability_state, dict)
                else {}
            ),
            "skills": (
                {str(key): value for key, value in s._runtime_skills_state.items()}
                if isinstance(s._runtime_skills_state, dict)
                else {}
            ),
            "safe_mode_enabled": bool(getattr(s, "_safe_mode_enabled", False)),
            "pending_follow_through_count": (
                len(s._proactive_state.get("pending_follow_through", []))
                if isinstance(s._proactive_state, dict)
                else 0
            ),
            "approval_pending_count": sum(
                1
                for row in (
                    s._proactive_state.get("approval_requests", [])
                    if isinstance(s._proactive_state, dict)
                    and isinstance(s._proactive_state.get("approval_requests"), list)
                    else []
                )
                if isinstance(row, dict) and str(row.get("status", "")).strip().lower() == "pending"
            ),
        },
    }
    try:
        runtime_payload["integrations"] = s._integration_health_snapshot()
    except Exception:
        runtime_payload["integrations"] = {}
    try:
        runtime_payload["dead_letter_queue"] = s._dead_letter_queue_status(limit=20, status_filter="open")
    except Exception:
        runtime_payload["dead_letter_queue"] = {}
    try:
        runtime_payload["recovery_journal"] = s._recovery_journal_status(limit=20)
    except Exception:
        runtime_payload["recovery_journal"] = {}

    explicit_entities = {
        item.strip().lower()
        for item in explicit_ha_entities
        if isinstance(item, str) and item.strip()
    }
    contract_entities = set(_collect_contract_entity_ids(due_rows))
    entity_ids = sorted(explicit_entities | contract_entities)
    if entity_ids:
        home_assistant: dict[str, Any] = {"entities": {}, "entity_errors": {}}
        runtime_payload["home_assistant"] = home_assistant
        ha_get_state = s._ha_get_state
        results = await asyncio.gather(
            *[ha_get_state(entity_id) for entity_id in entity_ids],
            return_exceptions=True,
        )
        for entity_id, result in zip(entity_ids, results):
            slot = _nested_home_assistant_entity_slot(runtime_payload, entity_id)
            if isinstance(result, Exception):
                slot["error"] = "exception"
                home_assistant["entity_errors"][entity_id] = "exception"
                continue
            payload, error_code = result
            if isinstance(payload, dict):
                slot["state"] = payload.get("state")
                slot["attributes"] = (
                    dict(payload.get("attributes"))
                    if isinstance(payload.get("attributes"), dict)
                    else {}
                )
                slot["last_changed"] = payload.get("last_changed")
                slot["last_updated"] = payload.get("last_updated")
            if error_code:
                slot["error"] = str(error_code)
                home_assistant["entity_errors"][entity_id] = str(error_code)
    return _deep_merge_dicts(runtime_payload, user_runtime_state)


def _update_world_model_state(world_model_state: dict[str, Any], *, runtime_state: dict[str, Any], now: float) -> int:
    entities = world_model_state.get("entities")
    if not isinstance(entities, dict):
        entities = {}
        world_model_state["entities"] = entities
    facts = world_model_state.get("facts")
    if not isinstance(facts, dict):
        facts = {}
        world_model_state["facts"] = facts
    events = world_model_state.get("events")
    if not isinstance(events, list):
        events = []
        world_model_state["events"] = events

    updated_entities = 0
    home_assistant = runtime_state.get("home_assistant")
    if isinstance(home_assistant, dict):
        nested = home_assistant.get("entities")
        if isinstance(nested, dict):
            for domain, domain_rows in nested.items():
                if not isinstance(domain_rows, dict):
                    continue
                domain_text = str(domain).strip().lower()
                if not domain_text:
                    continue
                for object_id, row in domain_rows.items():
                    if not isinstance(row, dict):
                        continue
                    object_text = str(object_id).strip().lower()
                    if not object_text:
                        continue
                    entity_id = f"{domain_text}.{object_text}"
                    entities[entity_id] = {
                        "entity_id": entity_id,
                        "state": row.get("state"),
                        "attributes": (
                            dict(row.get("attributes"))
                            if isinstance(row.get("attributes"), dict)
                            else {}
                        ),
                        "last_changed": row.get("last_changed"),
                        "last_updated": row.get("last_updated"),
                        "observed_at": now,
                    }
                    updated_entities += 1
    facts["runtime_safe_mode_enabled"] = bool(
        runtime_state.get("runtime", {}).get("safe_mode_enabled", False)
        if isinstance(runtime_state.get("runtime"), dict)
        else False
    )
    facts["runtime_approval_pending_count"] = int(
        runtime_state.get("runtime", {}).get("approval_pending_count", 0)
        if isinstance(runtime_state.get("runtime"), dict)
        else 0
    )
    events.append(
        {
            "type": "runtime_snapshot",
            "timestamp": now,
            "entity_update_count": updated_entities,
        }
    )
    if len(events) > 500:
        del events[: len(events) - 500]
    world_model_state["updated_at"] = now
    return updated_entities


def _update_goal_stack_progress(goal_stack: list[dict[str, Any]], rows: list[dict[str, Any]], *, now: float) -> None:
    goal_stats: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        goal_id = str(row.get("goal_id", "")).strip()
        if not goal_id:
            continue
        stats = goal_stats.setdefault(goal_id, {"total": 0, "completed": 0, "needs_replan": 0})
        stats["total"] += 1
        status = str(row.get("status", "")).strip().lower()
        if status == "completed":
            stats["completed"] += 1
        if status == "needs_replan":
            stats["needs_replan"] += 1

    for goal in goal_stack:
        if not isinstance(goal, dict):
            continue
        goal_id = str(goal.get("goal_id", "")).strip()
        if not goal_id:
            continue
        stats = goal_stats.get(goal_id, {"total": 0, "completed": 0, "needs_replan": 0})
        total = int(stats.get("total", 0) or 0)
        completed = int(stats.get("completed", 0) or 0)
        needs_replan = int(stats.get("needs_replan", 0) or 0)
        progress_pct = round((float(completed) / float(total)) * 100.0, 2) if total > 0 else 0.0
        goal["task_total"] = total
        goal["task_completed"] = completed
        goal["task_needs_replan"] = needs_replan
        goal["progress_pct"] = progress_pct
        goal["updated_at"] = now
        if total > 0 and completed >= total:
            goal["status"] = "completed"
        elif needs_replan > 0:
            goal["status"] = "blocked"
        elif total > 0:
            goal["status"] = "active"


def _autonomy_slo_snapshot(
    *,
    policy_engine: dict[str, Any],
    cycle_history: list[dict[str, Any]],
    backlog_step_count: int,
    now: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slo_policy = (
        policy_engine.get("autonomy_slo")
        if isinstance(policy_engine.get("autonomy_slo"), dict)
        else {}
    )
    window_size = 50
    window = [row for row in cycle_history[-window_size:] if isinstance(row, dict)]
    due_total = sum(int(row.get("due_count", 0) or 0) for row in window)
    executed_total = sum(int(row.get("executed_count", 0) or 0) for row in window)
    replan_total = sum(int(row.get("replan_count", 0) or 0) for row in window)
    verification_failure_total = sum(int(row.get("verification_failure_count", 0) or 0) for row in window)
    execution_rate = (float(executed_total) / float(due_total)) if due_total > 0 else 1.0
    replan_rate = (float(replan_total) / float(executed_total)) if executed_total > 0 else 0.0
    verification_failure_rate = (
        float(verification_failure_total) / float(executed_total)
        if executed_total > 0
        else 0.0
    )
    last_cycle_at = float(window[-1].get("timestamp", 0.0) or 0.0) if window else 0.0
    minutes_since_last_cycle = (now - last_cycle_at) / 60.0 if last_cycle_at > 0.0 else float("inf")

    max_replan_rate = float(slo_policy.get("max_replan_rate", 0.25) or 0.25)
    max_verification_failure_rate = float(
        slo_policy.get("max_verification_failure_rate", 0.2) or 0.2
    )
    max_backlog_steps = int(slo_policy.get("max_backlog_steps", 25) or 25)
    max_minutes_since_last_cycle = float(
        slo_policy.get("max_minutes_since_last_cycle", 30.0) or 30.0
    )

    alerts: list[dict[str, Any]] = []
    if replan_rate > max_replan_rate:
        alerts.append(
            {
                "severity": "high",
                "code": "autonomy_replan_rate_high",
                "message": (
                    f"Autonomy replan rate {replan_rate:.2f} exceeds policy threshold {max_replan_rate:.2f}."
                ),
                "observed": replan_rate,
                "threshold": max_replan_rate,
                "timestamp": now,
            }
        )
    if verification_failure_rate > max_verification_failure_rate:
        alerts.append(
            {
                "severity": "high",
                "code": "autonomy_verification_failure_rate_high",
                "message": (
                    "Autonomy verification failure rate "
                    f"{verification_failure_rate:.2f} exceeds threshold {max_verification_failure_rate:.2f}."
                ),
                "observed": verification_failure_rate,
                "threshold": max_verification_failure_rate,
                "timestamp": now,
            }
        )
    if backlog_step_count > max_backlog_steps:
        alerts.append(
            {
                "severity": "medium",
                "code": "autonomy_backlog_high",
                "message": f"Autonomy backlog {backlog_step_count} exceeds threshold {max_backlog_steps}.",
                "observed": backlog_step_count,
                "threshold": max_backlog_steps,
                "timestamp": now,
            }
        )
    if minutes_since_last_cycle > max_minutes_since_last_cycle:
        alerts.append(
            {
                "severity": "medium",
                "code": "autonomy_cycle_stale",
                "message": (
                    f"Autonomy cycle staleness {minutes_since_last_cycle:.1f}m exceeds "
                    f"threshold {max_minutes_since_last_cycle:.1f}m."
                ),
                "observed": minutes_since_last_cycle,
                "threshold": max_minutes_since_last_cycle,
                "timestamp": now,
            }
        )

    metrics = {
        "window_size": len(window),
        "due_total": due_total,
        "executed_total": executed_total,
        "execution_rate": round(execution_rate, 4),
        "replan_rate": round(replan_rate, 4),
        "verification_failure_rate": round(verification_failure_rate, 4),
        "backlog_step_count": int(backlog_step_count),
        "minutes_since_last_cycle": round(minutes_since_last_cycle, 4)
        if minutes_since_last_cycle != float("inf")
        else minutes_since_last_cycle,
    }
    return metrics, alerts


async def planner_autonomy_cycle(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _as_int = s._as_int
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response
    _slugify_identifier = s._slugify_identifier
    _retry_backoff_delay = s._retry_backoff_delay
    _generate_autonomy_replan_draft = s._generate_autonomy_replan_draft
    _autonomy_checkpoints = s._autonomy_checkpoints
    _autonomy_tasks = s._autonomy_tasks
    _autonomy_cycle_history = s._autonomy_cycle_history
    _autonomy_replan_drafts = s._autonomy_replan_drafts
    _world_model_state = s._world_model_state
    _goal_stack = s._goal_stack
    _autonomy_slo_state = s._autonomy_slo_state
    _policy_engine = s._policy_engine
    _proactive_state = s._proactive_state
    AUTONOMY_REPLAN_DRAFT_MAX = s.AUTONOMY_REPLAN_DRAFT_MAX
    AUTONOMY_CYCLE_HISTORY_MAX = s.AUTONOMY_CYCLE_HISTORY_MAX

    now = _as_float(args.get("now", time.time()), time.time(), minimum=0.0)
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    max_steps_per_task = _as_int(args.get("max_steps_per_task", 1), 1, minimum=1, maximum=10)
    approved_checkpoints = set(_as_str_list(args.get("approved_checkpoints"), lower=True))
    explicit_ha_entities = _as_str_list(args.get("ha_entities"), lower=True)
    user_runtime_state = args.get("runtime_state") if isinstance(args.get("runtime_state"), dict) else {}
    due_rows = [
        row
        for row in _autonomy_tasks()
        if str(row.get("status", "")).strip().lower() in {"scheduled", "waiting_checkpoint"}
        and float(row.get("execute_at", now + 1.0)) <= now
    ]
    due_rows.sort(key=lambda row: float(row.get("execute_at", now)))
    due_rows = due_rows[:limit]
    runtime_state = await _runtime_state_snapshot(
        user_runtime_state=user_runtime_state,
        due_rows=due_rows,
        explicit_ha_entities=explicit_ha_entities,
    )
    executed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    progressed_steps = 0
    retries_scheduled = 0
    replan_requests = 0
    replan_draft_count = 0
    verification_failures = 0
    world_model_entity_updates = _update_world_model_state(
        _world_model_state,
        runtime_state=runtime_state,
        now=now,
    )
    for row in due_rows:
        checkpoint_id = _slugify_identifier(str(row.get("checkpoint_id", "")).strip(), fallback="")
        requires_checkpoint = bool(row.get("requires_checkpoint", False))
        checkpoint_approved = bool(
            str(row.get("checkpoint_status", "")).strip().lower() == "approved"
            or (checkpoint_id and checkpoint_id in approved_checkpoints)
            or (
                checkpoint_id
                and bool(
                    isinstance(_autonomy_checkpoints.get(checkpoint_id), dict)
                    and _autonomy_checkpoints[checkpoint_id].get("approved")
                )
            )
        )
        if requires_checkpoint and not checkpoint_approved:
            row["status"] = "waiting_checkpoint"
            blocked.append(
                {
                    "id": str(row.get("id", "")),
                    "title": str(row.get("title", "")),
                    "checkpoint_id": checkpoint_id,
                    "reason": "checkpoint_required",
                }
            )
            continue
        if checkpoint_id:
            row["checkpoint_status"] = "approved"
            if checkpoint_id in _autonomy_checkpoints:
                _autonomy_checkpoints[checkpoint_id]["approved"] = True
                _autonomy_checkpoints[checkpoint_id]["updated_at"] = now
        row["needs_replan"] = False
        row["last_executed_at"] = now
        row["run_count"] = int(row.get("run_count", 0) or 0) + 1
        recurrence_sec = _as_float(row.get("recurrence_sec", 0.0), 0.0, minimum=0.0)
        task_payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        plan_steps_raw = row.get("plan_steps")
        plan_steps = (
            [str(item).strip() for item in plan_steps_raw if str(item).strip()]
            if isinstance(plan_steps_raw, list)
            else []
        )
        plan_total_steps = _as_int(
            row.get("plan_total_steps", len(plan_steps)),
            len(plan_steps),
            minimum=0,
            maximum=1000,
        )
        if plan_total_steps <= 0 and plan_steps:
            plan_total_steps = len(plan_steps)
        if plan_steps and plan_total_steps > len(plan_steps):
            plan_total_steps = len(plan_steps)
        plan_step_index = _as_int(
            row.get("plan_step_index", 0),
            0,
            minimum=0,
            maximum=max(0, plan_total_steps),
        )
        plan_step_attempts = _coerce_attempt_map(row.get("plan_step_attempts"))
        max_step_retries = _as_int(row.get("max_step_retries", 1), 1, minimum=0, maximum=5)
        retry_backoff_sec = _as_float(row.get("retry_backoff_sec", 15.0), 15.0, minimum=0.0, maximum=86_400.0)
        step_contracts = row.get("step_contracts") if isinstance(row.get("step_contracts"), list) else []
        pending_postcondition = (
            dict(row.get("pending_postcondition"))
            if isinstance(row.get("pending_postcondition"), dict)
            else {}
        )
        steps_executed = 0
        executed_steps: list[dict[str, Any]] = []
        failed_steps_cycle: list[dict[str, Any]] = []
        retry_scheduled = False
        postcondition_waiting = False
        needs_replan = False
        if plan_total_steps > 0 and plan_steps:
            completed_steps = (
                [item for item in row.get("plan_completed_steps", []) if isinstance(item, dict)]
                if isinstance(row.get("plan_completed_steps"), list)
                else []
            )
            failed_steps = (
                [item for item in row.get("plan_failed_steps", []) if isinstance(item, dict)]
                if isinstance(row.get("plan_failed_steps"), list)
                else []
            )
            while plan_step_index < plan_total_steps and steps_executed < max_steps_per_task:
                if plan_step_index >= len(plan_steps):
                    break
                step_text = str(plan_steps[plan_step_index]).strip()
                if not step_text:
                    plan_step_index += 1
                    continue
                step_number = plan_step_index + 1
                step_key = str(step_number)
                prior_attempts = int(plan_step_attempts.get(step_key, 0) or 0)
                attempt_number = prior_attempts + 1
                step_contract = (
                    step_contracts[plan_step_index]
                    if plan_step_index < len(step_contracts) and isinstance(step_contracts[plan_step_index], dict)
                    else {}
                )
                precondition = step_contract.get("precondition") if isinstance(step_contract, dict) else None
                postcondition = step_contract.get("postcondition") if isinstance(step_contract, dict) else None
                postcondition_configured = isinstance(postcondition, dict) and bool(postcondition)
                pending_step_number = _as_int(
                    pending_postcondition.get("step_number", 0),
                    0,
                    minimum=0,
                    maximum=max(0, plan_total_steps),
                )
                pending_attempt = _as_int(
                    pending_postcondition.get("attempt", 0),
                    0,
                    minimum=0,
                    maximum=100,
                )
                pending_for_step = bool(pending_postcondition) and pending_step_number == step_number
                if pending_for_step:
                    attempt_number = max(1, pending_attempt or int(plan_step_attempts.get(step_key, 1) or 1))
                    post_ok, post_evidence = _evaluate_condition(
                        postcondition,
                        row=row,
                        runtime_state=runtime_state,
                    )
                    if not post_ok:
                        verification_failures += 1
                        plan_step_attempts[step_key] = attempt_number
                        reason_code = str(post_evidence.get("reason_code", "postcondition_unmet"))
                        _record_failure_taxonomy(row, reason_code)
                        retry_allowed = attempt_number <= max_step_retries
                        failure_entry = {
                            "index": step_number,
                            "task": step_text,
                            "phase": "postcondition",
                            "reason_code": reason_code,
                            "attempt": attempt_number,
                            "max_step_retries": max_step_retries,
                            "failed_at": now,
                            "condition": post_evidence,
                            "will_retry": retry_allowed,
                        }
                        pending_postcondition = {}
                        if retry_allowed:
                            delay = _retry_backoff_delay(
                                max(0, attempt_number - 1),
                                base_delay_sec=retry_backoff_sec,
                                max_delay_sec=max(1.0, retry_backoff_sec * 16.0),
                            )
                            row["status"] = "scheduled"
                            row["execute_at"] = now + delay
                            retries_scheduled += 1
                            retry_scheduled = True
                            failure_entry["next_retry_at"] = row["execute_at"]
                        else:
                            row["status"] = "needs_replan"
                            row["needs_replan"] = True
                            row["replan_requested_at"] = now
                            replan_requests += 1
                            needs_replan = True
                            draft = await _generate_autonomy_replan_draft(
                                task_row=row,
                                reason_code=reason_code,
                                phase="postcondition",
                                runtime_state=runtime_state,
                            )
                            draft_id = f"replan-draft-{int(_proactive_state.get('autonomy_replan_seq', 1) or 1)}"
                            _proactive_state["autonomy_replan_seq"] = int(
                                _proactive_state.get("autonomy_replan_seq", 1) or 1
                            ) + 1
                            _autonomy_replan_drafts[draft_id] = {
                                "draft_id": draft_id,
                                "task_id": str(row.get("id", "")),
                                "task_title": str(row.get("title", "")),
                                "status": "pending",
                                "created_at": now,
                                "reason_code": reason_code,
                                "phase": "postcondition",
                                "source": str(draft.get("source", "fallback")),
                                "rationale": str(draft.get("rationale", "")),
                                "plan_steps": (
                                    list(draft.get("plan_steps", []))
                                    if isinstance(draft.get("plan_steps"), list)
                                    else []
                                ),
                                "step_contracts": (
                                    list(draft.get("step_contracts", []))
                                    if isinstance(draft.get("step_contracts"), list)
                                    else []
                                ),
                            }
                            if len(_autonomy_replan_drafts) > AUTONOMY_REPLAN_DRAFT_MAX:
                                oldest = sorted(
                                    _autonomy_replan_drafts.items(),
                                    key=lambda pair: float(pair[1].get("created_at", 0.0) or 0.0),
                                )[: len(_autonomy_replan_drafts) - AUTONOMY_REPLAN_DRAFT_MAX]
                                for key, _ in oldest:
                                    _autonomy_replan_drafts.pop(key, None)
                            row["latest_replan_draft_id"] = draft_id
                            replan_draft_count += 1
                            _proactive_state["pending_follow_through"].append(
                                {
                                    "created_at": now,
                                    "task": f"Replan autonomy task: {str(row.get('title', 'autonomy task')).strip() or 'autonomy task'}",
                                    "payload": {
                                        "autonomy_task_id": str(row.get("id", "")),
                                        "replan_draft_id": draft_id,
                                        "plan_step_index": step_number,
                                        "plan_total_steps": plan_total_steps,
                                        "reason": reason_code,
                                        "phase": "postcondition",
                                    },
                                }
                            )
                        row["last_failure_reason"] = reason_code
                        failed_steps.append(failure_entry)
                        failed_steps_cycle.append(dict(failure_entry))
                        executed_steps.append(
                            {
                                "index": step_number,
                                "task": step_text,
                                "attempt": attempt_number,
                                "verification": "postcondition_failed",
                            }
                        )
                        break

                    pending_postcondition = {}
                    plan_step_attempts.pop(step_key, None)
                    completed_steps.append(
                        {
                            "index": step_number,
                            "task": step_text,
                            "attempt": attempt_number,
                            "completed_at": now,
                        }
                    )
                    plan_step_index += 1
                    steps_executed += 1
                    progressed_steps += 1
                    row["last_step_at"] = now
                    row["last_failure_reason"] = ""
                    executed_steps.append(
                        {
                            "index": step_number,
                            "task": step_text,
                            "attempt": attempt_number,
                            "verification": "ok",
                        }
                    )
                    continue

                pre_ok, pre_evidence = _evaluate_condition(
                    precondition,
                    row=row,
                    runtime_state=runtime_state,
                )
                if not pre_ok:
                    verification_failures += 1
                    plan_step_attempts[step_key] = attempt_number
                    reason_code = str(pre_evidence.get("reason_code", "precondition_unmet"))
                    _record_failure_taxonomy(row, reason_code)
                    retry_allowed = attempt_number <= max_step_retries
                    failure_entry = {
                        "index": step_number,
                        "task": step_text,
                        "phase": "precondition",
                        "reason_code": reason_code,
                        "attempt": attempt_number,
                        "max_step_retries": max_step_retries,
                        "failed_at": now,
                        "condition": pre_evidence,
                        "will_retry": retry_allowed,
                    }
                    if retry_allowed:
                        delay = _retry_backoff_delay(
                            max(0, attempt_number - 1),
                            base_delay_sec=retry_backoff_sec,
                            max_delay_sec=max(1.0, retry_backoff_sec * 16.0),
                        )
                        row["status"] = "scheduled"
                        row["execute_at"] = now + delay
                        retries_scheduled += 1
                        retry_scheduled = True
                        failure_entry["next_retry_at"] = row["execute_at"]
                    else:
                        row["status"] = "needs_replan"
                        row["needs_replan"] = True
                        row["replan_requested_at"] = now
                        replan_requests += 1
                        needs_replan = True
                        draft = await _generate_autonomy_replan_draft(
                            task_row=row,
                            reason_code=reason_code,
                            phase="precondition",
                            runtime_state=runtime_state,
                        )
                        draft_id = f"replan-draft-{int(_proactive_state.get('autonomy_replan_seq', 1) or 1)}"
                        _proactive_state["autonomy_replan_seq"] = int(
                            _proactive_state.get("autonomy_replan_seq", 1) or 1
                        ) + 1
                        _autonomy_replan_drafts[draft_id] = {
                            "draft_id": draft_id,
                            "task_id": str(row.get("id", "")),
                            "task_title": str(row.get("title", "")),
                            "status": "pending",
                            "created_at": now,
                            "reason_code": reason_code,
                            "phase": "precondition",
                            "source": str(draft.get("source", "fallback")),
                            "rationale": str(draft.get("rationale", "")),
                            "plan_steps": (
                                list(draft.get("plan_steps", []))
                                if isinstance(draft.get("plan_steps"), list)
                                else []
                            ),
                            "step_contracts": (
                                list(draft.get("step_contracts", []))
                                if isinstance(draft.get("step_contracts"), list)
                                else []
                            ),
                        }
                        if len(_autonomy_replan_drafts) > AUTONOMY_REPLAN_DRAFT_MAX:
                            oldest = sorted(
                                _autonomy_replan_drafts.items(),
                                key=lambda pair: float(pair[1].get("created_at", 0.0) or 0.0),
                            )[: len(_autonomy_replan_drafts) - AUTONOMY_REPLAN_DRAFT_MAX]
                            for key, _ in oldest:
                                _autonomy_replan_drafts.pop(key, None)
                        row["latest_replan_draft_id"] = draft_id
                        replan_draft_count += 1
                        _proactive_state["pending_follow_through"].append(
                            {
                                "created_at": now,
                                "task": f"Replan autonomy task: {str(row.get('title', 'autonomy task')).strip() or 'autonomy task'}",
                                "payload": {
                                    "autonomy_task_id": str(row.get("id", "")),
                                    "replan_draft_id": draft_id,
                                    "plan_step_index": step_number,
                                    "plan_total_steps": plan_total_steps,
                                    "reason": reason_code,
                                    "phase": "precondition",
                                },
                            }
                        )
                    row["last_failure_reason"] = reason_code
                    failed_steps.append(failure_entry)
                    failed_steps_cycle.append(dict(failure_entry))
                    break

                attempt_number = int(plan_step_attempts.get(step_key, 0) or 0) + 1
                _proactive_state["pending_follow_through"].append(
                    {
                        "created_at": now,
                        "task": step_text,
                        "payload": {
                            "autonomy_task_id": str(row.get("id", "")),
                            "plan_step_index": step_number,
                            "plan_total_steps": plan_total_steps,
                            "attempt": attempt_number,
                            **{str(k): v for k, v in task_payload.items()},
                        },
                    }
                )
                if postcondition_configured:
                    verification_delay_sec = _as_float(
                        step_contract.get("verification_delay_sec", row.get("postcondition_delay_sec", 2.0))
                        if isinstance(step_contract, dict)
                        else row.get("postcondition_delay_sec", 2.0),
                        2.0,
                        minimum=0.0,
                        maximum=600.0,
                    )
                    row["status"] = "scheduled"
                    row["execute_at"] = now + verification_delay_sec
                    pending_postcondition = {
                        "step_number": step_number,
                        "attempt": attempt_number,
                        "queued_at": now,
                        "verify_after": row["execute_at"],
                    }
                    postcondition_waiting = True
                    executed_steps.append(
                        {
                            "index": step_number,
                            "task": step_text,
                            "attempt": attempt_number,
                            "verification": "pending_postcondition",
                        }
                    )
                    break

                plan_step_attempts.pop(step_key, None)
                completed_steps.append(
                    {
                        "index": step_number,
                        "task": step_text,
                        "attempt": attempt_number,
                        "completed_at": now,
                    }
                )
                plan_step_index += 1
                steps_executed += 1
                progressed_steps += 1
                row["last_step_at"] = now
                executed_steps.append(
                    {
                        "index": step_number,
                        "task": step_text,
                        "attempt": attempt_number,
                        "verification": "ok",
                    }
                )
            row["plan_failed_steps"] = failed_steps[-200:]
            row["plan_completed_steps"] = completed_steps[-200:]
            row["plan_step_attempts"] = plan_step_attempts
            row["plan_step_index"] = plan_step_index
            row["pending_postcondition"] = dict(pending_postcondition)
            row["plan_total_steps"] = plan_total_steps
            row["progress_pct"] = round(
                (float(plan_step_index) / float(plan_total_steps)) * 100.0,
                2,
            ) if plan_total_steps > 0 else 0.0
            if plan_step_index < plan_total_steps:
                if str(row.get("status", "")).strip().lower() != "needs_replan":
                    if not retry_scheduled and not postcondition_waiting:
                        cadence_sec = _as_float(
                            row.get("step_cadence_sec", 300.0),
                            300.0,
                            minimum=0.0,
                            maximum=86_400.0 * 7.0,
                        )
                        row["status"] = "scheduled"
                        row["execute_at"] = now + cadence_sec
            else:
                row["last_failure_reason"] = ""
                row["pending_postcondition"] = {}
                row["plan_last_completed_at"] = now
                if recurrence_sec > 0.0:
                    row["status"] = "scheduled"
                    row["execute_at"] = now + recurrence_sec
                    row["plan_step_index"] = 0
                    row["plan_step_attempts"] = {}
                    row["progress_pct"] = 0.0
                else:
                    row["status"] = "completed"
        else:
            task_text = str(task_payload.get("task") or task_payload.get("action") or row.get("title", "")).strip()
            if task_text:
                _proactive_state["pending_follow_through"].append(
                    {
                        "created_at": now,
                        "task": task_text,
                        "payload": {str(k): v for k, v in task_payload.items()},
                    }
                )
            if recurrence_sec > 0.0:
                row["status"] = "scheduled"
                row["execute_at"] = now + recurrence_sec
            else:
                row["status"] = "completed"
        executed.append(
            {
                "id": str(row.get("id", "")),
                "title": str(row.get("title", "")),
                "status": str(row.get("status", "")),
                "run_count": int(row.get("run_count", 0) or 0),
                "steps_executed": steps_executed,
                "executed_steps": executed_steps,
                "plan_step_index": int(row.get("plan_step_index", 0) or 0),
                "plan_total_steps": int(row.get("plan_total_steps", 0) or 0),
                "progress_pct": float(row.get("progress_pct", 0.0) or 0.0),
                "retry_scheduled": retry_scheduled,
                "needs_replan": needs_replan,
                "failed_steps": failed_steps_cycle,
                "last_failure_reason": str(row.get("last_failure_reason", "")),
                "latest_replan_draft_id": str(row.get("latest_replan_draft_id", "")),
            }
        )
    tracked_rows = _autonomy_tasks()
    backlog_step_count = 0
    in_progress_count = 0
    needs_replan_count = 0
    for row in tracked_rows:
        if not isinstance(row, dict):
            continue
        total_steps = _as_int(row.get("plan_total_steps", 0), 0, minimum=0, maximum=1000)
        if total_steps <= 0:
            continue
        index = _as_int(row.get("plan_step_index", 0), 0, minimum=0, maximum=total_steps)
        backlog_step_count += max(0, total_steps - index)
        status = str(row.get("status", "")).strip().lower()
        if status in {"scheduled", "waiting_checkpoint"} and index > 0:
            in_progress_count += 1
        if status == "needs_replan":
            needs_replan_count += 1
    _update_goal_stack_progress(_goal_stack, tracked_rows, now=now)
    cycle_summary = {
        "timestamp": now,
        "due_count": len(due_rows),
        "executed_count": len(executed),
        "blocked_count": len(blocked),
        "progressed_step_count": progressed_steps,
        "retry_scheduled_count": retries_scheduled,
        "verification_failure_count": verification_failures,
        "replan_count": replan_requests,
        "replan_draft_count": replan_draft_count,
        "world_model_entity_updates": world_model_entity_updates,
    }
    _autonomy_cycle_history.append(cycle_summary)
    if len(_autonomy_cycle_history) > AUTONOMY_CYCLE_HISTORY_MAX:
        del _autonomy_cycle_history[: len(_autonomy_cycle_history) - AUTONOMY_CYCLE_HISTORY_MAX]
    slo_metrics, slo_alerts = _autonomy_slo_snapshot(
        policy_engine=_policy_engine if isinstance(_policy_engine, dict) else {},
        cycle_history=_autonomy_cycle_history,
        backlog_step_count=backlog_step_count,
        now=now,
    )
    _autonomy_slo_state["updated_at"] = now
    _autonomy_slo_state["window_size"] = int(slo_metrics.get("window_size", 0) or 0)
    _autonomy_slo_state["metrics"] = {str(key): value for key, value in slo_metrics.items()}
    _autonomy_slo_state["alerts"] = [dict(row) for row in slo_alerts][:200]
    cycle_summary["slo_alert_count"] = len(slo_alerts)
    payload = {
        "action": "autonomy_cycle",
        "cycle": cycle_summary,
        "executed": executed,
        "blocked": blocked,
        "pending_follow_through_count": len(_proactive_state.get("pending_follow_through", [])),
        "backlog_step_count": backlog_step_count,
        "in_progress_count": in_progress_count,
        "needs_replan_count": needs_replan_count,
        "replan_draft_count": replan_draft_count,
        "goal_stack_depth": len(_goal_stack),
        "slo": {
            "metrics": slo_metrics,
            "alerts": slo_alerts,
        },
    }
    risk = (
        "high"
        if replan_requests > 0 or bool(slo_alerts)
        else "medium"
        if (blocked or verification_failures > 0)
        else "low"
    )
    record_summary("planner_engine", "ok", start_time, effect=f"autonomy_cycle:{len(executed)}", risk=risk)
    return _expansion_payload_response(payload)
