"""Recovery and dead-letter helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_recovery_runtime import (
    append_dead_letter_entry as _runtime_append_dead_letter_entry,
    dead_letter_enqueue as _runtime_dead_letter_enqueue,
    dead_letter_matches as _runtime_dead_letter_matches,
    dead_letter_queue_status as _runtime_dead_letter_queue_status,
    read_dead_letter_entries as _runtime_read_dead_letter_entries,
    read_recovery_journal_entries as _runtime_read_recovery_journal_entries,
    recovery_begin as _runtime_recovery_begin,
    recovery_finish as _runtime_recovery_finish,
    recovery_journal_status as _runtime_recovery_journal_status,
    recovery_reconcile_interrupted as _runtime_recovery_reconcile_interrupted,
    tool_response_success as _runtime_tool_response_success,
    tool_response_text as _runtime_tool_response_text,
    write_dead_letter_entries as _runtime_write_dead_letter_entries,
    write_recovery_journal_entry as _runtime_write_recovery_journal_entry,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def read_recovery_journal_entries() -> list[dict[str, Any]]:
    return _runtime_read_recovery_journal_entries(_services_module())


def write_recovery_journal_entry(payload: dict[str, Any]) -> None:
    _runtime_write_recovery_journal_entry(_services_module(), payload)


def recovery_begin(tool_name: str, *, operation: str, context: dict[str, Any] | None = None) -> str:
    return _runtime_recovery_begin(
        _services_module(),
        tool_name,
        operation=operation,
        context=context,
    )


def recovery_finish(
    entry_id: str,
    *,
    tool_name: str,
    operation: str,
    status: str,
    detail: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    _runtime_recovery_finish(
        _services_module(),
        entry_id,
        tool_name=tool_name,
        operation=operation,
        status=status,
        detail=detail,
        context=context,
    )


def recovery_reconcile_interrupted() -> None:
    _runtime_recovery_reconcile_interrupted(_services_module())


def recovery_journal_status(*, limit: int = 20) -> dict[str, Any]:
    return _runtime_recovery_journal_status(_services_module(), limit=limit)


def read_dead_letter_entries() -> list[dict[str, Any]]:
    return _runtime_read_dead_letter_entries(_services_module())


def write_dead_letter_entries(entries: list[dict[str, Any]]) -> None:
    _runtime_write_dead_letter_entries(_services_module(), entries)


def append_dead_letter_entry(entry: dict[str, Any]) -> None:
    _runtime_append_dead_letter_entry(_services_module(), entry)


def dead_letter_matches(entry: dict[str, Any], *, status_filter: str) -> bool:
    return _runtime_dead_letter_matches(entry, status_filter=status_filter)


def dead_letter_queue_status(*, limit: int = 20, status_filter: str = "open") -> dict[str, Any]:
    return _runtime_dead_letter_queue_status(
        _services_module(),
        limit=limit,
        status_filter=status_filter,
    )


def dead_letter_enqueue(tool_name: str, args: dict[str, Any], *, reason: str, detail: str = "") -> str | None:
    return _runtime_dead_letter_enqueue(
        _services_module(),
        tool_name,
        args,
        reason=reason,
        detail=detail,
    )


def tool_response_text(result: dict[str, Any]) -> str:
    return _runtime_tool_response_text(result)


def tool_response_success(text: str) -> bool:
    return _runtime_tool_response_success(text)
