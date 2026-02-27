# Jarvis TODO — Wave 48 (Planner Schedule Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 27
- Completed: 27
- Remaining: 0

---

## A) Scope and baseline

- [x] `W48-A01` Confirm Wave 47 merged and branch baseline clean.
- [x] `W48-A02` Re-profile largest remaining service-domain modules.
- [x] `W48-A03` Select `services_domains/planner_schedule.py` for decomposition.
- [x] `W48-A04` Preserve API compatibility via export shim.

## B) Decomposition design

- [x] `W48-B01` Define `planner_timers.py` for timer handlers.
- [x] `W48-B02` Define `planner_reminders.py` for reminder handlers and reminder payload helpers.
- [x] `W48-B03` Keep runtime behavior and lazy services binding unchanged.

## C) Extraction implementation

- [x] `W48-C01` Create `services_domains/planner_timers.py`.
- [x] `W48-C02` Move `timer_create`, `timer_list`, `timer_cancel`.
- [x] `W48-C03` Create `services_domains/planner_reminders.py`.
- [x] `W48-C04` Move `_list_reminder_payloads`, `_due_unnotified_reminder_payloads`.
- [x] `W48-C05` Move `reminder_create`, `reminder_list`, `reminder_complete`, `reminder_notify_due`.

## D) Compatibility and boundaries

- [x] `W48-D01` Replace `services_domains/planner_schedule.py` with compatibility exports.
- [x] `W48-D02` Keep imports used by `services_domains/planner.py` stable.
- [x] `W48-D03` Add import-boundary check for `planner_timers`.
- [x] `W48-D04` Add import-boundary check for `planner_reminders`.

## E) Validation

- [x] `W48-E01` Run focused lint on planner schedule modules + boundary test file.
- [x] `W48-E02` Run targeted pytest for timer/reminder handlers + boundaries.
- [x] `W48-E03` Run full `make check`.
- [x] `W48-E04` Run full `make security-gate`.
- [x] `W48-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W48-F01` Capture post-split line-count outcomes.
- [x] `W48-F02` Commit and push Wave 48.

---

## Outcome snapshot (completed)

- Planner schedule decomposition:
  - `services_domains/planner_schedule.py`: `535 -> 25` lines (compatibility exports)
  - New `services_domains/planner_timers.py`: `201` lines
  - New `services_domains/planner_reminders.py`: `346` lines
- Boundary enforcement:
  - Added import-boundary coverage for new planner timer/reminder modules.
- Validation status:
  - `make check`: `634 passed`
  - `make security-gate`: `634 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
