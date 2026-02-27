# Jarvis TODO — Wave 15 (Services Bind + State Bootstrap Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 5
- Completed: 5
- Remaining: 0

---

## A) Decomposition

- [x] `W15-S01` Extract `services.bind(...)` runtime initialization/bootstrap into `src/jarvis/tools/services_runtime_state.py`.
- [x] `W15-S02` Extract expansion-state helpers (`_replace_state_dict`, `_expansion_state_payload`, `_persist_expansion_state`, `_load_expansion_state`) into `services_runtime_state.py`.
- [x] `W15-S03` Keep compatibility wrappers in `src/jarvis/tools/services.py` so existing imports/callers continue to use the same function names.
- [x] `W15-S04` Address time-of-day flakiness in `test_reminder_notify_due_dispatches_and_marks_notified` by making the policy explicit (`interrupt`) in test setup.

## B) Quality and verification

- [x] `W15-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New runtime bootstrap module: `src/jarvis/tools/services_runtime_state.py`.
- `src/jarvis/tools/services.py` now delegates bind/state-bootstrap responsibilities to that module.
- `src/jarvis/tools/services.py` reduced to `3,730` lines (from `4,102` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
