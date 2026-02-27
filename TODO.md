# Jarvis TODO — Wave 18 (Status Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 4
- Completed: 4
- Remaining: 0

---

## A) Decomposition

- [x] `W18-S01` Extract status/snapshot helpers from `services.py` into `src/jarvis/tools/services_status_runtime.py` (`integration`, `identity`, `voice`, `observability`, and expansion snapshots).
- [x] `W18-S02` Extract scorecard utility chain (`_health_rollup`, `_score_label`, `_recent_tool_rows`, `_duration_p95_ms`, `_jarvis_scorecard_snapshot`) into `services_status_runtime.py`.
- [x] `W18-S03` Keep compatibility wrappers in `services.py` for all moved status/scorecard helper function names.

## B) Quality and verification

- [x] `W18-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New status runtime helper module: `src/jarvis/tools/services_status_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,997` lines (from `3,401` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
