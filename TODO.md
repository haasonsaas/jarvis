# Jarvis TODO — Wave 56 (Home Mutation Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 25
- Completed: 25
- Remaining: 0

---

## A) Scope and baseline

- [x] `W56-A01` Re-profile large `services_domains` modules after Wave 55.
- [x] `W56-A02` Select `services_domains/home_mutation.py` as next hotspot.
- [x] `W56-A03` Preserve `smart_home` API contract and message behavior.

## B) Decomposition design

- [x] `W56-B01` Extract policy/validation/state-preflight checks into `home_mutation_preflight.py`.
- [x] `W56-B02` Extract dry-run/execution/audit pipeline into `home_mutation_execute.py`.
- [x] `W56-B03` Reduce `home_mutation.py` to orchestration wrapper.

## C) Extraction implementation

- [x] `W56-C01` Create `services_domains/home_mutation_preflight.py`.
- [x] `W56-C02` Move domain/action/entity/data validation logic.
- [x] `W56-C03` Move identity, confirm, sensitive-target, and area-policy checks.
- [x] `W56-C04` Move preview-gate and preflight state/no-op logic.
- [x] `W56-C05` Create `services_domains/home_mutation_execute.py`.
- [x] `W56-C06` Move post-authorization audit envelope.
- [x] `W56-C07` Move dry-run response/feedback flow.
- [x] `W56-C08` Move HA execute/recovery/error handling flow.
- [x] `W56-C09` Rewrite `home_mutation.py` as thin wrapper.

## D) Boundaries and quality

- [x] `W56-D01` Add import-boundary check for `home_mutation_preflight`.
- [x] `W56-D02` Add import-boundary check for `home_mutation_execute`.
- [x] `W56-D03` Preserve lazy service-access pattern in extracted modules.

## E) Validation

- [x] `W56-E01` Run focused lint for mutation modules + boundary test file.
- [x] `W56-E02` Run targeted `smart_home` tests from `test_tools_services.py`.
- [x] `W56-E03` Run `tests/test_import_boundaries.py`.
- [x] `W56-E04` Run full `make check`.
- [x] `W56-E05` Run full `make security-gate`.
- [x] `W56-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W56-F01` Record post-split line-count outcomes.
- [x] `W56-F02` Commit Wave 56 changes.
- [x] `W56-F03` Push Wave 56 to remote.

---

## Outcome snapshot (completed)

- Home mutation decomposition:
  - `services_domains/home_mutation.py`: `373 -> 45` lines (wrapper).
  - New `services_domains/home_mutation_preflight.py`: `263` lines.
  - New `services_domains/home_mutation_execute.py`: `162` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both extracted home-mutation modules.
- Validation status:
  - Focused lint: pass.
  - Targeted `smart_home` tests: pass (`41 passed`, `181 deselected`).
  - `tests/test_import_boundaries.py`: pass (`65 passed`).
  - `make check`: `654 passed`.
  - `make security-gate`: `654 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
