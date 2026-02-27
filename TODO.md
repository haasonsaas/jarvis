# Jarvis TODO — Wave 17 (Identity Runtime Decomposition)

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

- [x] `W17-S01` Extract identity context/audit/domain helpers from `services.py` into `src/jarvis/tools/services_identity_runtime.py`.
- [x] `W17-S02` Extract identity authorization decision flow (`_identity_authorize`) into `services_identity_runtime.py`.
- [x] `W17-S03` Keep compatibility wrappers in `services.py` for `_identity_context`, `_identity_audit_fields`, `_identity_trust_domain`, `_identity_authorize`, and `_identity_enriched_audit`.

## B) Quality and verification

- [x] `W17-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New identity runtime helper module: `src/jarvis/tools/services_identity_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `3,401` lines (from `3,571` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
