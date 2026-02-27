# Jarvis TODO — Wave 54 (Planner Reminders Decomposition)

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

- [x] `W54-A01` Re-profile large `services_domains` modules after Wave 53.
- [x] `W54-A02` Select `planner_reminders.py` as next decomposition target.
- [x] `W54-A03` Preserve reminder tool API contract (`create/list/complete/notify`).

## B) Decomposition design

- [x] `W54-B01` Extract reminder create/list/complete into `planner_reminders_crud.py`.
- [x] `W54-B02` Extract due notification flow into `planner_reminders_notify.py`.
- [x] `W54-B03` Keep `planner_reminders.py` as thin export surface.

## C) Extraction implementation

- [x] `W54-C01` Create `services_domains/planner_reminders_crud.py`.
- [x] `W54-C02` Move `_list_reminder_payloads` helper.
- [x] `W54-C03` Move `reminder_create` logic.
- [x] `W54-C04` Move `reminder_list` logic.
- [x] `W54-C05` Move `reminder_complete` logic.
- [x] `W54-C06` Create `services_domains/planner_reminders_notify.py`.
- [x] `W54-C07` Move `_due_unnotified_reminder_payloads` helper.
- [x] `W54-C08` Move `reminder_notify_due` logic.
- [x] `W54-C09` Rewrite `planner_reminders.py` to re-export public handlers.

## D) Boundaries and quality

- [x] `W54-D01` Add import-boundary check for `planner_reminders_crud`.
- [x] `W54-D02` Add import-boundary check for `planner_reminders_notify`.
- [x] `W54-D03` Keep runtime helper imports isolated from `jarvis.tools.services`.

## E) Validation

- [x] `W54-E01` Run focused lint for reminder modules + boundary test file.
- [x] `W54-E02` Run targeted reminder lifecycle/notification tests.
- [x] `W54-E03` Run `tests/test_import_boundaries.py`.
- [x] `W54-E04` Run full `make check`.
- [x] `W54-E05` Run full `make security-gate`.
- [x] `W54-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W54-F01` Record post-split line-count outcomes.
- [x] `W54-F02` Commit Wave 54 changes.
- [x] `W54-F03` Push Wave 54 to remote.

---

## Outcome snapshot (completed)

- Planner reminder decomposition:
  - `services_domains/planner_reminders.py`: `346 -> 17` lines (thin exports).
  - New `services_domains/planner_reminders_crud.py`: `197` lines.
  - New `services_domains/planner_reminders_notify.py`: `163` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both new reminder modules.
- Validation status:
  - Focused lint: pass.
  - Reminder targeted tests: pass.
  - `tests/test_import_boundaries.py`: pass.
  - `make check`: `650 passed`.
  - `make security-gate`: `650 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
