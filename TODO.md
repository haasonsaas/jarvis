# Jarvis TODO — Wave 44 (Home HA Tools Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 29
- Completed: 29
- Remaining: 0

---

## A) Scope and baseline

- [x] `W44-A01` Confirm Wave 43 merged and working tree baseline.
- [x] `W44-A02` Re-profile domain module sizes after comms decomposition.
- [x] `W44-A03` Select `services_domains/home_ha_tools.py` as next hotspot.
- [x] `W44-A04` Preserve existing import/registration API via compatibility module.

## B) Decomposition design

- [x] `W44-B01` Define conversation-only module boundary.
- [x] `W44-B02` Define to-do-only module boundary.
- [x] `W44-B03` Define timer-only module boundary.
- [x] `W44-B04` Define area/media module boundary.
- [x] `W44-B05` Retain lazy `services` binding pattern inside each module.

## C) Module extraction

- [x] `W44-C01` Create `services_domains/home_ha_conversation.py`.
- [x] `W44-C02` Move `home_assistant_conversation` without behavior changes.
- [x] `W44-C03` Create `services_domains/home_ha_todo.py`.
- [x] `W44-C04` Move `home_assistant_todo` without behavior changes.
- [x] `W44-C05` Create `services_domains/home_ha_timer.py`.
- [x] `W44-C06` Move `home_assistant_timer` without behavior changes.
- [x] `W44-C07` Create `services_domains/home_ha_area_media.py`.
- [x] `W44-C08` Move `home_assistant_area_entities` and `media_control` without behavior changes.

## D) Compatibility and boundaries

- [x] `W44-D01` Replace `services_domains/home_ha_tools.py` with compatibility exports.
- [x] `W44-D02` Keep `home_control.py` and `home.py` import behavior unchanged.
- [x] `W44-D03` Add import-boundary check for `home_ha_conversation`.
- [x] `W44-D04` Add import-boundary check for `home_ha_todo`.
- [x] `W44-D05` Add import-boundary check for `home_ha_timer`.
- [x] `W44-D06` Add import-boundary check for `home_ha_area_media`.

## E) Validation

- [x] `W44-E01` Run focused lint on new Home HA modules + boundary test file.
- [x] `W44-E02` Run targeted pytest selection for Home HA handlers + boundaries.
- [x] `W44-E03` Run full `make check`.
- [x] `W44-E04` Run full `make security-gate`.
- [x] `W44-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W44-F01` Capture post-split line-count outcomes.
- [x] `W44-F02` Commit and push Wave 44.

---

## Outcome snapshot (completed)

- Home HA decomposition:
  - `services_domains/home_ha_tools.py`: `882 -> 19` lines (compatibility exports)
  - New `services_domains/home_ha_conversation.py`: `268` lines
  - New `services_domains/home_ha_todo.py`: `189` lines
  - New `services_domains/home_ha_timer.py`: `171` lines
  - New `services_domains/home_ha_area_media.py`: `290` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new Home HA modules.
- Validation status:
  - `make check`: `620 passed`
  - `make security-gate`: `620 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
