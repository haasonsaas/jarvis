# Jarvis TODO — Wave 43 (Comms Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 28
- Completed: 28
- Remaining: 0

---

## A) Scope and baseline

- [x] `W43-A01` Confirm Wave 42 is merged and working tree is clean.
- [x] `W43-A02` Identify next largest service-domain concentration after Wave 42.
- [x] `W43-A03` Select `services_domains/comms.py` for decomposition.
- [x] `W43-A04` Preserve current import surface with compatibility exports.

## B) Module extraction plan

- [x] `W43-B01` Define notifications split (`slack_notify`, `discord_notify`, `pushover_notify`).
- [x] `W43-B02` Define email split (`email_send`, `email_summary`).
- [x] `W43-B03` Define Todoist split (`todoist_add_task`, `todoist_list_tasks`).
- [x] `W43-B04` Keep runtime lazy-binding pattern (`_services`) per module.

## C) Implement notifications module

- [x] `W43-C01` Create `services_domains/comms_notifications.py`.
- [x] `W43-C02` Move `slack_notify` without behavioral changes.
- [x] `W43-C03` Move `discord_notify` without behavioral changes.
- [x] `W43-C04` Move `pushover_notify` without behavioral changes.

## D) Implement email module

- [x] `W43-D01` Create `services_domains/comms_email.py`.
- [x] `W43-D02` Move `email_send` without behavioral changes.
- [x] `W43-D03` Move `email_summary` without behavioral changes.

## E) Implement Todoist module

- [x] `W43-E01` Create `services_domains/comms_todoist.py`.
- [x] `W43-E02` Move `todoist_add_task` without behavioral changes.
- [x] `W43-E03` Move `todoist_list_tasks` without behavioral changes.

## F) Compatibility and boundaries

- [x] `W43-F01` Replace `services_domains/comms.py` with compatibility re-exports.
- [x] `W43-F02` Keep import paths used by `services.py` and `services_server.py` stable.
- [x] `W43-F03` Add import-boundary check for `comms_notifications`.
- [x] `W43-F04` Add import-boundary check for `comms_email`.
- [x] `W43-F05` Add import-boundary check for `comms_todoist`.

## G) Validation

- [x] `W43-G01` Run focused lint on touched domain modules and boundary test file.
- [x] `W43-G02` Run targeted pytest selection for comms handlers and boundaries.
- [x] `W43-G03` Run full `make check` suite.
- [x] `W43-G04` Run `make security-gate`.
- [x] `W43-G05` Run `./scripts/jarvis_readiness.sh fast`.

## H) Release loop

- [x] `W43-H01` Record line-count outcomes for decomposed comms domain.
- [x] `W43-H02` Commit and push Wave 43.

---

## Outcome snapshot (completed)

- Comms decomposition:
  - `services_domains/comms.py`: `913 -> 27` lines (compatibility exports)
  - New `services_domains/comms_notifications.py`: `415` lines
  - New `services_domains/comms_email.py`: `186` lines
  - New `services_domains/comms_todoist.py`: `332` lines
- Boundary enforcement:
  - Added import-boundary coverage for new comms domain modules.
- Validation status:
  - Focused lint complete.
  - Remaining validation gates tracked above and executed in this wave.
