# Jarvis TODO — Wave 30 (Coercion Runtime Decomposition)

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

- [x] `W30-S01` Extract core coercion helpers from `services.py` into `src/jarvis/tools/services_coercion_runtime.py` (`_as_bool`, `_as_int`, `_as_exact_int`, `_as_float`, `_effective_act_timeout`, `_as_str_list`).
- [x] `W30-S02` Replace extracted coercion helpers in `services.py` with compatibility wrappers.
- [x] `W30-S03` Preserve behavior parity for non-finite and fractional numeric coercion paths after extraction.

## B) Quality and verification

- [x] `W30-Q01` Re-run targeted coercion/memory regression tests for non-finite and fractional inputs.
- [x] `W30-Q02` Re-run full `make check`, `make security-gate`, and readiness full suite.

---

## Outcome snapshot (current)

- New coercion runtime helper module: `src/jarvis/tools/services_coercion_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `1,685` lines (from `1,773` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
