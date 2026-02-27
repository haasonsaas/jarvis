"""Recovery journal runtime helpers for services domains."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any

def read_recovery_journal_entries(services_module: Any) -> list[dict[str, Any]]:
    s = services_module
    path = s._recovery_journal_path
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


def write_recovery_journal_entry(services_module: Any, payload: dict[str, Any]) -> None:
    s = services_module
    path = s._recovery_journal_path
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, default=str)
    try:
        with path.open("a") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        s.log.warning("Failed to write recovery journal entry: %s", exc)


def recovery_begin(
    services_module: Any,
    tool_name: str,
    *,
    operation: str,
    context: dict[str, Any] | None = None,
) -> str:
    entry_id = secrets.token_hex(12)
    write_recovery_journal_entry(
        services_module,
        {
            "timestamp": time.time(),
            "entry_id": entry_id,
            "tool": str(tool_name),
            "operation": str(operation),
            "status": "started",
            "context": context or {},
        },
    )
    return entry_id


def recovery_finish(
    services_module: Any,
    entry_id: str,
    *,
    tool_name: str,
    operation: str,
    status: str,
    detail: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    write_recovery_journal_entry(
        services_module,
        {
            "timestamp": time.time(),
            "entry_id": str(entry_id),
            "tool": str(tool_name),
            "operation": str(operation),
            "status": str(status),
            "detail": str(detail),
            "context": context or {},
        },
    )


class RecoveryOperation:
    def __init__(
        self,
        services_module: Any,
        tool_name: str,
        *,
        operation: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._services_module = services_module
        self._tool_name = str(tool_name)
        self._operation = str(operation)
        self._base_context = dict(context or {})
        self._context_updates: dict[str, Any] = {}
        self._status = "failed"
        self._detail = ""
        self._closed = False
        self._entry_id = recovery_begin(
            self._services_module,
            self._tool_name,
            operation=self._operation,
            context=self._base_context,
        )

    def mark_completed(self, *, detail: str = "ok", context: dict[str, Any] | None = None) -> None:
        self._status = "completed"
        self._detail = str(detail)
        if context:
            self._context_updates.update(context)

    def mark_failed(self, detail: str, *, context: dict[str, Any] | None = None) -> None:
        self._status = "failed"
        self._detail = str(detail)
        if context:
            self._context_updates.update(context)

    def mark_cancelled(self, *, detail: str = "cancelled", context: dict[str, Any] | None = None) -> None:
        self._status = "cancelled"
        self._detail = str(detail)
        if context:
            self._context_updates.update(context)

    def __enter__(self) -> RecoveryOperation:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: Any,
    ) -> bool:
        if self._closed:
            return False
        status = self._status
        detail = self._detail
        if exc is not None:
            if isinstance(exc, asyncio.CancelledError):
                status = "cancelled"
                if not detail:
                    detail = "cancelled"
            else:
                status = "failed"
                if not detail:
                    detail = exc.__class__.__name__
        if not detail:
            detail = "ok" if status == "completed" else "failed"
        context = {**self._base_context, **self._context_updates}
        recovery_finish(
            self._services_module,
            self._entry_id,
            tool_name=self._tool_name,
            operation=self._operation,
            status=status,
            detail=detail,
            context=context,
        )
        self._closed = True
        return False


def recovery_operation(
    services_module: Any,
    tool_name: str,
    *,
    operation: str,
    context: dict[str, Any] | None = None,
) -> RecoveryOperation:
    return RecoveryOperation(services_module, tool_name, operation=operation, context=context)


def recovery_reconcile_interrupted(services_module: Any) -> None:
    entries = read_recovery_journal_entries(services_module)
    if not entries:
        return
    latest_by_entry: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry.get("entry_id", "")).strip()
        if not entry_id:
            continue
        latest_by_entry[entry_id] = entry
    for entry_id, entry in latest_by_entry.items():
        status = str(entry.get("status", "")).strip().lower()
        if status != "started":
            continue
        recovery_finish(
            services_module,
            entry_id,
            tool_name=str(entry.get("tool", "unknown")),
            operation=str(entry.get("operation", "unknown")),
            status="interrupted",
            detail="process_restart",
            context={"source": "reconcile"},
        )


def recovery_journal_status(services_module: Any, *, limit: int = 20) -> dict[str, Any]:
    s = services_module
    entries = read_recovery_journal_entries(s)
    latest_by_entry: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry.get("entry_id", "")).strip()
        if not entry_id:
            continue
        latest_by_entry[entry_id] = entry
    unresolved = sum(
        1
        for entry in latest_by_entry.values()
        if str(entry.get("status", "")).strip().lower() == "started"
    )
    interrupted = sum(
        1
        for entry in latest_by_entry.values()
        if str(entry.get("status", "")).strip().lower() == "interrupted"
    )
    size = max(1, min(100, int(limit)))
    recent = entries[-size:]
    return {
        "path": str(s._recovery_journal_path),
        "exists": s._recovery_journal_path.exists(),
        "entry_count": len(entries),
        "tracked_actions": len(latest_by_entry),
        "unresolved_count": unresolved,
        "interrupted_count": interrupted,
        "recent": recent,
    }
