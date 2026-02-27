# Jarvis TODO — Wave 40 (Home Domain Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 26
- Completed: 26
- Remaining: 0

---

## A) Scope and baseline

- [x] `W40-A01` Identify next largest post-W39 hotspot by line count.
- [x] `W40-A02` Select `services_domains/home.py` for decomposition.
- [x] `W40-A03` Define split boundaries that preserve existing tool entrypoints.

## B) Home domain split

- [x] `W40-B01` Create `services_domains/home_state.py` for state/capabilities handlers.
- [x] `W40-B02` Move `smart_home_state` into `home_state.py`.
- [x] `W40-B03` Move `home_assistant_capabilities` into `home_state.py`.
- [x] `W40-B04` Create `services_domains/home_orchestrator.py` for orchestration handler.
- [x] `W40-B05` Move `home_orchestrator` into `home_orchestrator.py`.
- [x] `W40-B06` Create `services_domains/home_control.py` for smart-home control and HA tool handlers.
- [x] `W40-B07` Move `smart_home` into `home_control.py`.
- [x] `W40-B08` Move `home_assistant_conversation` into `home_control.py`.
- [x] `W40-B09` Move `home_assistant_todo` into `home_control.py`.
- [x] `W40-B10` Move `home_assistant_timer` into `home_control.py`.
- [x] `W40-B11` Move `home_assistant_area_entities` into `home_control.py`.
- [x] `W40-B12` Move `media_control` into `home_control.py`.

## C) Compatibility and API stability

- [x] `W40-C01` Replace `services_domains/home.py` with compatibility re-exports.
- [x] `W40-C02` Preserve existing import sites in `services.py` and `services_server.py` without API break.
- [x] `W40-C03` Add explicit `__all__` in compatibility module for stable export surface.

## D) Safety boundaries and tests

- [x] `W40-D01` Extend import-boundary tests for `home_state`.
- [x] `W40-D02` Extend import-boundary tests for `home_orchestrator`.
- [x] `W40-D03` Extend import-boundary tests for `home_control`.
- [x] `W40-D04` Run targeted home-domain pytest scenarios across all moved handlers.

## E) Quality gates

- [x] `W40-E01` Run focused lint on new/changed home domain modules.
- [x] `W40-E02` Run `make check` full suite.
- [x] `W40-E03` Run `make security-gate`.
- [x] `W40-E04` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W40-F01` Update TODO completion snapshot with measured size changes.
- [x] `W40-F02` Commit and push Wave 40.

---

## Outcome snapshot (completed)

- Home domain decomposition completed:
  - `services_domains/home.py`: `1801 -> 29` lines (compatibility exports only)
  - New `services_domains/home_state.py`: `186` lines
  - New `services_domains/home_orchestrator.py`: `398` lines
  - New `services_domains/home_control.py`: `1243` lines
- Behavior continuity:
  - Existing tool API/registration surface preserved through compatibility exports.
  - Targeted tool tests for moved handlers remained green.
- Validation status:
  - `make check`: `606 passed`
  - `make security-gate`: `606 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
