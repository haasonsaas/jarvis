"""Dead-letter queue runtime helpers for services domains."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

def read_dead_letter_entries(services_module: Any) -> list[dict[str, Any]]:
    s = services_module
    path = s._dead_letter_queue_path
    if not path.exists():
        return []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def write_dead_letter_entries(services_module: Any, entries: list[dict[str, Any]]) -> None:
    s = services_module
    path = s._dead_letter_queue_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, default=str) for item in entries if isinstance(item, dict)]
    text = "\n".join(lines)
    if text:
        text += "\n"
    try:
        path.write_text(text)
    except OSError as exc:
        s.log.warning("Failed to write dead-letter queue: %s", exc)


def append_dead_letter_entry(services_module: Any, entry: dict[str, Any]) -> None:
    s = services_module
    path = s._dead_letter_queue_path
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str)
    try:
        with path.open("a") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        s.log.warning("Failed to append dead-letter queue entry: %s", exc)


def dead_letter_matches(entry: dict[str, Any], *, status_filter: str) -> bool:
    status = str(entry.get("status", "pending")).strip().lower() or "pending"
    if status_filter == "all":
        return True
    if status_filter == "open":
        return status in {"pending", "failed"}
    return status == status_filter


def dead_letter_queue_status(
    services_module: Any,
    *,
    limit: int = 20,
    status_filter: str = "open",
) -> dict[str, Any]:
    s = services_module
    entries = read_dead_letter_entries(s)
    size = max(1, min(200, int(limit)))
    selected = [entry for entry in entries if dead_letter_matches(entry, status_filter=status_filter)]
    recent_raw = selected[-size:]
    recent: list[dict[str, Any]] = []
    for entry in recent_raw:
        tool_name = str(entry.get("tool", "unknown")).strip().lower()
        args = entry.get("args")
        args_preview = s._sanitize_inbound_payload(args if isinstance(args, dict) else {})
        recent.append(
            {
                "entry_id": str(entry.get("entry_id", "")),
                "timestamp": float(entry.get("timestamp", 0.0) or 0.0),
                "tool": tool_name,
                "status": str(entry.get("status", "pending")),
                "reason": str(entry.get("reason", "")),
                "attempts": int(entry.get("attempts", 0) or 0),
                "last_attempt_at": float(entry.get("last_attempt_at", 0.0) or 0.0),
                "last_error": str(entry.get("last_error", "")),
                "args_preview": args_preview,
                "replayable": tool_name
                in {
                    "webhook_trigger",
                    "slack_notify",
                    "discord_notify",
                    "email_send",
                    "pushover_notify",
                },
            }
        )
    pending = sum(1 for entry in entries if str(entry.get("status", "pending")).strip().lower() == "pending")
    failed = sum(1 for entry in entries if str(entry.get("status", "")).strip().lower() == "failed")
    replayed = sum(1 for entry in entries if str(entry.get("status", "")).strip().lower() == "replayed")
    return {
        "path": str(s._dead_letter_queue_path),
        "exists": s._dead_letter_queue_path.exists(),
        "entry_count": len(entries),
        "pending_count": pending,
        "failed_count": failed,
        "replayed_count": replayed,
        "recent": recent,
    }


def dead_letter_enqueue(
    services_module: Any,
    tool_name: str,
    args: dict[str, Any],
    *,
    reason: str,
    detail: str = "",
) -> str | None:
    s = services_module
    if not isinstance(args, dict):
        return None
    if bool(args.get("_dead_letter_replay")):
        return None
    payload_args = {str(key): value for key, value in args.items() if str(key) != "_dead_letter_replay"}
    entry_id = secrets.token_hex(10)
    entry = {
        "timestamp": time.time(),
        "entry_id": entry_id,
        "tool": str(tool_name),
        "status": "pending",
        "reason": str(reason),
        "attempts": 0,
        "last_attempt_at": 0.0,
        "last_error": str(detail),
        "args": payload_args,
    }
    append_dead_letter_entry(s, entry)
    s._audit(
        "dead_letter_queue",
        {
            "result": "enqueued",
            "entry_id": entry_id,
            "tool": str(tool_name),
            "reason": str(reason),
        },
    )
    return entry_id

