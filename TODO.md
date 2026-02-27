# Jarvis TODO — Wave 26 (Circuit-Breaker Runtime Decomposition)

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

- [x] `W26-S01` Extract integration mapping + circuit-breaker state helpers from `services.py` into `src/jarvis/tools/services_circuit_runtime.py` (`_integration_for_tool`, `_ensure_circuit_breaker_state`, `_integration_circuit_open`).
- [x] `W26-S02` Extract circuit-breaker mutation/snapshot/message helpers (`_integration_record_failure`, `_integration_record_success`, `_integration_circuit_snapshot`, `_integration_circuit_open_message`) into `services_circuit_runtime.py`.
- [x] `W26-S03` Replace extracted functions in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W26-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New circuit runtime helper module: `src/jarvis/tools/services_circuit_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `1,933` lines (from `1,982` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
