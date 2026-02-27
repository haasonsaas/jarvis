# Jarvis TODO — Wave 20 (Recovery and Dead-Letter Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 6
- Completed: 6
- Remaining: 0

---

## A) Decomposition

- [x] `W20-S01` Extract recovery journal helpers from `services.py` into `src/jarvis/tools/services_recovery_runtime.py` (`_read/_write_recovery_journal_entries`, `_recovery_begin`, `_recovery_finish`, `_recovery_reconcile_interrupted`, `_recovery_journal_status`).
- [x] `W20-S02` Extract dead-letter queue helpers into `services_recovery_runtime.py` (`_read/_write/_append_dead_letter_entries`, `_dead_letter_matches`, `_dead_letter_queue_status`, `_dead_letter_enqueue`).
- [x] `W20-S03` Extract replay utility helpers into `services_recovery_runtime.py` (`_tool_response_text`, `_tool_response_success`).
- [x] `W20-S04` Replace extracted functions in `services.py` with compatibility wrappers and preserve `_RecoveryOperation` compatibility surface.

## B) Behavioral parity

- [x] `W20-B01` Preserve existing recovery/dead-letter semantics and audit behavior while delegating to runtime module.

## C) Quality and verification

- [x] `W20-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New recovery runtime helper module: `src/jarvis/tools/services_recovery_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,576` lines (from `2,817` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
