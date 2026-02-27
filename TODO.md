# Jarvis TODO — Wave 22 (Audit Retention and Status Runtime Decomposition)

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

- [x] `W22-S01` Extract audit status helper from `services.py` into `src/jarvis/tools/services_audit_runtime.py` (`_audit_status`).
- [x] `W22-S02` Extract audit retention helpers into `services_audit_runtime.py` (`_prune_audit_file`, `_apply_retention_policies`) with behavioral parity.
- [x] `W22-S03` Replace extracted functions in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W22-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- Extended audit runtime helper module: `src/jarvis/tools/services_audit_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,282` lines (from `2,361` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
