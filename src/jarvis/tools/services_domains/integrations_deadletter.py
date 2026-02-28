"""Dead-letter integration handlers."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def dead_letter_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _record_service_error = s._record_service_error
    _dead_letter_queue_status = s._dead_letter_queue_status
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("dead_letter_list"):
        record_summary("dead_letter_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    status_filter = str(args.get("status", "open")).strip().lower() or "open"
    if status_filter not in {"open", "all", "pending", "failed", "replayed"}:
        _record_service_error("dead_letter_list", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "status must be one of open, all, pending, failed, replayed."}]}
    payload = _dead_letter_queue_status(limit=limit, status_filter=status_filter)
    payload["status_filter"] = status_filter
    record_summary("dead_letter_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


async def dead_letter_replay(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _as_int = s._as_int
    _read_dead_letter_entries = s._read_dead_letter_entries
    _dead_letter_matches = s._dead_letter_matches
    webhook_trigger = s.webhook_trigger
    slack_notify = s.slack_notify
    discord_notify = s.discord_notify
    email_send = s.email_send
    pushover_notify = s.pushover_notify
    _tool_response_text = s._tool_response_text
    _tool_response_success = s._tool_response_success
    _write_dead_letter_entries = s._write_dead_letter_entries
    time = s.time
    _audit = s._audit
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("dead_letter_replay"):
        record_summary("dead_letter_replay", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    status_filter = str(args.get("status", "open")).strip().lower() or "open"
    if status_filter not in {"open", "all", "pending", "failed", "replayed"}:
        _record_service_error("dead_letter_replay", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "status must be one of open, all, pending, failed, replayed."}]}
    entry_id = str(args.get("entry_id", "")).strip()
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    dry_run = _as_bool(args.get("dry_run"), default=False)
    entries = _read_dead_letter_entries()
    if not entries:
        record_summary("dead_letter_replay", "empty", start_time)
        return {"content": [{"type": "text", "text": "Dead-letter queue is empty."}]}

    replay_handlers: dict[str, Any] = {
        "webhook_trigger": webhook_trigger,
        "slack_notify": slack_notify,
        "discord_notify": discord_notify,
        "email_send": email_send,
        "pushover_notify": pushover_notify,
    }
    selected_indexes: list[int] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        item_entry_id = str(entry.get("entry_id", "")).strip()
        if entry_id and item_entry_id != entry_id:
            continue
        if not _dead_letter_matches(entry, status_filter=status_filter):
            continue
        tool_name = str(entry.get("tool", "")).strip().lower()
        if tool_name not in replay_handlers:
            continue
        selected_indexes.append(idx)
        if not entry_id and len(selected_indexes) >= limit:
            break
    if not selected_indexes:
        record_summary("dead_letter_replay", "empty", start_time)
        return {"content": [{"type": "text", "text": "No matching dead-letter entries to replay."}]}

    replayed_count = 0
    failed_count = 0
    results: list[dict[str, Any]] = []
    for idx in selected_indexes:
        entry = entries[idx]
        tool_name = str(entry.get("tool", "")).strip().lower()
        handler = replay_handlers.get(tool_name)
        if handler is None:
            continue
        if dry_run:
            results.append(
                {
                    "entry_id": str(entry.get("entry_id", "")),
                    "tool": tool_name,
                    "status": str(entry.get("status", "unknown")),
                    "result": "dry_run",
                }
            )
            continue
        payload_raw = entry.get("args")
        payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
        payload["_dead_letter_replay"] = True
        replay_text = ""
        success = False
        try:
            replay_result = await handler(payload)
            replay_text = _tool_response_text(replay_result)
            success = _tool_response_success(replay_text)
        except Exception as exc:
            replay_text = f"{exc.__class__.__name__}: {exc}"
            success = False
        attempts = 0
        try:
            attempts = int(entry.get("attempts", 0) or 0)
        except (TypeError, ValueError):
            attempts = 0
        entry["attempts"] = attempts + 1
        entry["last_attempt_at"] = time.time()
        entry["last_error"] = "" if success else replay_text[:300]
        entry["status"] = "replayed" if success else "failed"
        if success:
            replayed_count += 1
        else:
            failed_count += 1
        results.append(
            {
                "entry_id": str(entry.get("entry_id", "")),
                "tool": tool_name,
                "status": str(entry.get("status", "unknown")),
                "result": replay_text[:300],
            }
        )
    if not dry_run:
        _write_dead_letter_entries(entries)
    if dry_run:
        record_summary("dead_letter_replay", "ok", start_time, "dry_run")
    elif failed_count > 0 and replayed_count == 0:
        record_summary("dead_letter_replay", "error", start_time, "replay_failed")
    else:
        record_summary("dead_letter_replay", "ok", start_time)
    payload = {
        "requested_entry_id": entry_id,
        "dry_run": dry_run,
        "attempted_count": len(selected_indexes),
        "replayed_count": replayed_count,
        "failed_count": failed_count,
        "results": results,
    }
    _audit(
        "dead_letter_replay",
        {
            "result": "dry_run" if dry_run else ("ok" if failed_count == 0 else "partial"),
            "attempted_count": len(selected_indexes),
            "replayed_count": replayed_count,
            "failed_count": failed_count,
            "dry_run": dry_run,
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}
