# Jarvis TODO — Wave 59 (Area + Media Handler Decomposition)

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

## A) Scope and baseline

- [x] `W59-A01` Re-profile high-line home domain modules after Wave 58.
- [x] `W59-A02` Select `services_domains/home_ha_area_media.py` for decomposition.
- [x] `W59-A03` Preserve API contract for `home_assistant_area_entities` and `media_control`.

## B) Decomposition design

- [x] `W59-B01` Extract area entity lookup flow to `home_area_entities_tool.py`.
- [x] `W59-B02` Extract media action flow to `home_media_control_tool.py`.
- [x] `W59-B03` Reduce `home_ha_area_media.py` to thin exports.

## C) Extraction implementation

- [x] `W59-C01` Create `services_domains/home_area_entities_tool.py`.
- [x] `W59-C02` Move area template/render/filter/state-include logic.
- [x] `W59-C03` Create `services_domains/home_media_control_tool.py`.
- [x] `W59-C04` Move media action validation, policy, preview, and execution logic.
- [x] `W59-C05` Replace `home_ha_area_media.py` with export facade.

## D) Boundaries and quality

- [x] `W59-D01` Add import-boundary check for `home_area_entities_tool`.
- [x] `W59-D02` Add import-boundary check for `home_media_control_tool`.
- [x] `W59-D03` Preserve lazy access pattern for service helpers.

## E) Validation

- [x] `W59-E01` Run focused lint for changed modules + boundary test file.
- [x] `W59-E02` Run targeted tests for area-entities/media-control paths.
- [x] `W59-E03` Run `tests/test_import_boundaries.py`.
- [x] `W59-E04` Run full `make check`.
- [x] `W59-E05` Run full `make security-gate`.
- [x] `W59-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W59-F01` Capture post-split line-count outcomes.
- [x] `W59-F02` Commit Wave 59 changes.
- [x] `W59-F03` Push Wave 59 to remote.

---

## Outcome snapshot (completed)

- Area/media decomposition:
  - `services_domains/home_ha_area_media.py`: `290 -> 8` lines (thin exports).
  - New `services_domains/home_area_entities_tool.py`: `109` lines.
  - New `services_domains/home_media_control_tool.py`: `197` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both new home area/media modules.
- Validation status:
  - Focused lint: pass.
  - Targeted tests: pass (`2 passed`, `220 deselected`).
  - `tests/test_import_boundaries.py`: pass (`71 passed`).
  - `make check`: `660 passed`.
  - `make security-gate`: `660 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
