# Jarvis TODO — Wave 7 (Further Service Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 10
- Completed: 10
- Remaining: 0

---

## A) Domain extraction continuation

- [x] `W7-S01` Extract `skills_governance` out of `services.py`.
- [x] `W7-S02` Extract `quality_evaluator` out of `services.py`.
- [x] `W7-S03` Extract `embodiment_presence` out of `services.py`.
- [x] `W7-S04` Extract helper `_skills_snapshot_rows` alongside governance handlers.
- [x] `W7-S05` Add new domain module `src/jarvis/tools/services_domains/governance.py`.
- [x] `W7-S06` Rewire `services.py` imports to load governance handlers from domain module.

## B) Integrity and verification

- [x] `W7-V01` Keep MCP tool registrations and schema mappings unchanged after extraction.
- [x] `W7-V02` Re-run targeted service/runtime regression tests.
- [x] `W7-V03` Re-run full lint/tests/security/readiness gates.
- [x] `W7-V04` Update docs tree to reflect additional domain module.

---

## Outcome

- `services.py` reduced further from `9,660` lines to `9,341` lines in this wave.
- All local quality and readiness gates are passing.
