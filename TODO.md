# Jarvis TODO — Wave 10 (Governance + Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 9
- Completed: 4
- Remaining: 5

---

## A) Service decomposition

- [x] `W10-S01` Extract `skills_list`, `skills_enable`, `skills_disable`, and `skills_version` from `services.py` into `services_domains/governance.py`.
- [x] `W10-S02` Extract `system_status`, `system_status_contract`, and `jarvis_scorecard` from `services.py` into `services_domains/governance.py`.
- [x] `W10-S03` Rewire `services.py` imports and remove legacy implementations for extracted governance handlers.
- [-] `W10-S04` Extract timer runtime handlers (`timer_create`, `timer_list`, `timer_cancel`) into `services_domains/planner.py`.
- [ ] `W10-S05` Extract reminder runtime handlers (`reminder_create`, `reminder_list`, `reminder_complete`, `reminder_notify_due`) into `services_domains/planner.py`.
- [ ] `W10-S06` Extract task-plan runtime handlers (`task_plan_create`, `task_plan_list`, `task_plan_update`, `task_plan_summary`, `task_plan_next`) into `services_domains/planner.py`.
- [ ] `W10-S07` Extract Home Assistant state/capabilities handlers (`smart_home_state`, `home_assistant_capabilities`) into `services_domains/home.py`.

## B) Quality and verification

- [x] `W10-Q01` Re-run `make check`, `make security-gate`, readiness full suite, and strict eval dataset after governance extraction.
- [ ] `W10-Q02` Re-run full quality gates after completing remaining Wave 10 extraction items.

---

## Outcome snapshot (current)

- `services.py` is now `6,708` lines (down from `7,278` before this wave and `8,890` before Waves 9/10).
- `services_domains/governance.py` now owns skills lifecycle + status contract + scorecard runtime handlers.
- Full tests pass (`555 passed`), security gate passes, and strict eval contract remains green (`91/91`).
