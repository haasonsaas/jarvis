# Jarvis TODO — Wave 14 (Operator Control Decomposition)

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

- [x] `W14-S01` Extract `Jarvis._operator_control_handler` command-dispatch logic from `src/jarvis/__main__.py` into `src/jarvis/runtime_operator_control.py`.
- [x] `W14-S02` Keep public/operator entrypoint compatibility by leaving `Jarvis._operator_control_handler(...)` as a thin delegating wrapper.
- [x] `W14-S03` Preserve control-policy enums and output payload behavior for wake modes, timeout profiles, personality controls, runtime profile import/export, skills actions, and webhook clearing.

## B) Quality and verification

- [x] `W14-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after the extraction.

---

## Outcome snapshot (current)

- `src/jarvis/__main__.py` now delegates operator action handling to `src/jarvis/runtime_operator_control.py`.
- `src/jarvis/__main__.py` reduced to `2,919` lines (from `3,258` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
