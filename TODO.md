# Jarvis TODO — Wave 55 (Todoist Domain Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 24
- Completed: 24
- Remaining: 0

---

## A) Scope and baseline

- [x] `W55-A01` Re-profile remaining large communications domain files.
- [x] `W55-A02` Select `services_domains/comms_todoist.py` for decomposition.
- [x] `W55-A03` Preserve Todoist tool API contract (`add_task`, `list_tasks`).

## B) Decomposition design

- [x] `W55-B01` Extract task creation flow to `comms_todoist_add.py`.
- [x] `W55-B02` Extract task listing flow to `comms_todoist_list.py`.
- [x] `W55-B03` Keep `comms_todoist.py` as thin export facade.

## C) Extraction implementation

- [x] `W55-C01` Create `services_domains/comms_todoist_add.py`.
- [x] `W55-C02` Move `todoist_add_task` request/validation/recovery logic.
- [x] `W55-C03` Create `services_domains/comms_todoist_list.py`.
- [x] `W55-C04` Move `todoist_list_tasks` retry/formatting logic.
- [x] `W55-C05` Replace `comms_todoist.py` body with export surface.

## D) Boundaries and quality

- [x] `W55-D01` Add import-boundary check for `comms_todoist_add`.
- [x] `W55-D02` Add import-boundary check for `comms_todoist_list`.
- [x] `W55-D03` Keep lazy service loading pattern in extracted modules.

## E) Validation

- [x] `W55-E01` Run focused lint for Todoist modules + boundary test file.
- [x] `W55-E02` Run targeted Todoist tool tests from `test_tools_services.py`.
- [x] `W55-E03` Run `tests/test_import_boundaries.py`.
- [x] `W55-E04` Run full `make check`.
- [x] `W55-E05` Run full `make security-gate`.
- [x] `W55-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W55-F01` Capture post-split line-count outcomes.
- [x] `W55-F02` Commit Wave 55 changes.
- [x] `W55-F03` Push Wave 55 to remote.

---

## Outcome snapshot (completed)

- Todoist domain decomposition:
  - `services_domains/comms_todoist.py`: `332 -> 8` lines (thin exports).
  - New `services_domains/comms_todoist_add.py`: `176` lines.
  - New `services_domains/comms_todoist_list.py`: `169` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both new Todoist modules.
- Validation status:
  - Focused lint: pass.
  - Todoist targeted tests: pass (`28 passed`, `194 deselected`).
  - `tests/test_import_boundaries.py`: pass (`63 passed`).
  - `make check`: `652 passed`.
  - `make security-gate`: `652 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
