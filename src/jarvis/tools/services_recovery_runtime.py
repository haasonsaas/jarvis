"""Compatibility wrapper for recovery and dead-letter runtime helpers."""

from __future__ import annotations

from jarvis.tools.services_dead_letter_runtime import (
    append_dead_letter_entry,
    dead_letter_enqueue,
    dead_letter_matches,
    dead_letter_queue_status,
    read_dead_letter_entries,
    write_dead_letter_entries,
)
from jarvis.tools.services_recovery_journal_runtime import (
    RecoveryOperation,
    read_recovery_journal_entries,
    recovery_begin,
    recovery_finish,
    recovery_journal_status,
    recovery_operation,
    recovery_reconcile_interrupted,
    write_recovery_journal_entry,
)
from jarvis.tools.services_recovery_response_runtime import (
    tool_response_success,
    tool_response_text,
)

__all__ = [
    "RecoveryOperation",
    "append_dead_letter_entry",
    "dead_letter_enqueue",
    "dead_letter_matches",
    "dead_letter_queue_status",
    "read_dead_letter_entries",
    "read_recovery_journal_entries",
    "recovery_begin",
    "recovery_finish",
    "recovery_journal_status",
    "recovery_operation",
    "recovery_reconcile_interrupted",
    "tool_response_success",
    "tool_response_text",
    "write_dead_letter_entries",
    "write_recovery_journal_entry",
]
