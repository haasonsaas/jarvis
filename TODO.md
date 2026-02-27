# Jarvis TODO — Wave 12 (Policy + Main Runtime Decomposition)

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

- [x] `W12-S01` Extract service policy/routing constants from `services.py` into `tools/service_policy.py`.
- [x] `W12-S02` Extract `__main__.py` runtime constant block into `runtime_constants.py`.
- [x] `W12-S03` Extract `__main__.py` audio utility helpers into `audio/runtime_audio.py`.

## B) Quality and verification

- [x] `W12-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after Wave 12 extraction items.

---

## Outcome snapshot (current)

- `services.py` now imports policy constants from `tools/service_policy.py` and schema contracts from `tools/service_schemas.py`.
- `src/jarvis/__main__.py` now imports runtime behavior constants from `runtime_constants.py`.
- `src/jarvis/__main__.py` now delegates audio conversion/resampling helpers to `audio/runtime_audio.py`.
- `services.py` reduced to `4,551` lines and `src/jarvis/__main__.py` reduced to `3,404` lines.
- Full gates are green: `make check` (`555 passed`), `make security-gate`, and readiness full suite (`91/91` strict eval).
