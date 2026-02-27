# Jarvis TODO — Wave 41 (Home Control Subdomain Split)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 22
- Completed: 22
- Remaining: 0

---

## A) Scope and rationale

- [x] `W41-A01` Re-evaluate Wave 40 output and identify largest remaining home-domain file.
- [x] `W41-A02` Select `services_domains/home_control.py` for second-level split.
- [x] `W41-A03` Define split boundary: mutating control vs HA utility tools.

## B) Subdomain extraction

- [x] `W41-B01` Create `services_domains/home_mutation.py`.
- [x] `W41-B02` Move `smart_home` into `home_mutation.py`.
- [x] `W41-B03` Create `services_domains/home_ha_tools.py`.
- [x] `W41-B04` Move `home_assistant_conversation` into `home_ha_tools.py`.
- [x] `W41-B05` Move `home_assistant_todo` into `home_ha_tools.py`.
- [x] `W41-B06` Move `home_assistant_timer` into `home_ha_tools.py`.
- [x] `W41-B07` Move `home_assistant_area_entities` into `home_ha_tools.py`.
- [x] `W41-B08` Move `media_control` into `home_ha_tools.py`.

## C) Compatibility surface

- [x] `W41-C01` Convert `services_domains/home_control.py` into compatibility re-exports.
- [x] `W41-C02` Preserve existing import path behavior for upstream modules/tests.
- [x] `W41-C03` Add explicit `__all__` export contract for home-control compatibility module.

## D) Safety and test boundaries

- [x] `W41-D01` Add import-boundary test for `home_mutation` module.
- [x] `W41-D02` Add import-boundary test for `home_ha_tools` module.
- [x] `W41-D03` Re-run targeted home tool tests for moved handlers.

## E) Quality gates

- [x] `W41-E01` Run focused lint for changed files.
- [x] `W41-E02` Run `make check` full suite.
- [x] `W41-E03` Run `make security-gate`.
- [x] `W41-E04` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W41-F01` Capture resulting line-count deltas.
- [x] `W41-F02` Commit and push Wave 41.

---

## Outcome snapshot (completed)

- Additional decomposition completed:
  - `services_domains/home_control.py`: `1242 -> 21` lines (compatibility exports)
  - New `services_domains/home_mutation.py`: `373` lines
  - New `services_domains/home_ha_tools.py`: `882` lines
- Combined home domain structure after Wave 41:
  - `home.py` (compat): `29` lines
  - `home_state.py`: `186` lines
  - `home_orchestrator.py`: `398` lines
  - `home_control.py` (compat): `21` lines
  - `home_mutation.py`: `373` lines
  - `home_ha_tools.py`: `882` lines
- Validation status:
  - `make check`: `608 passed`
  - `make security-gate`: `608 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
