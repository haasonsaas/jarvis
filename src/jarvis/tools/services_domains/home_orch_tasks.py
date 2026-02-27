"""Task-run handlers for home orchestrator."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_orch_task_start(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _home_task_runs = s._home_task_runs
    _as_float = s._as_float
    HOME_TASK_MAX_TRACKED = s.HOME_TASK_MAX_TRACKED

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
    return _expansion_payload_response({"action": "task_start", "task": row, "task_count": len(_home_task_runs)})


async def home_orch_task_update(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _expansion_payload_response = s._expansion_payload_response
    _home_task_runs = s._home_task_runs
    _as_float = s._as_float

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
    return _expansion_payload_response({"action": "task_update", "task": dict(row)})


async def home_orch_task_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response
    _home_task_runs = s._home_task_runs
    _as_int = s._as_int

    limit = _as_int(args.get("limit", 50), 50, minimum=1, maximum=200)
    tasks = sorted(_home_task_runs.values(), key=lambda row: float(row.get("updated_at", 0.0)), reverse=True)[:limit]
    record_summary("home_orchestrator", "ok", start_time, effect="task_list", risk="low")
    return _expansion_payload_response({"action": "task_list", "task_count": len(_home_task_runs), "tasks": tasks})
