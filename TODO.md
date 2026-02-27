# Jarvis TODO — Wave 67 (State + Email + Task-Plan Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 35
- Completed: 35
- Remaining: 0

---

## A) Scope and baseline

- [x] `W67-A01` Profile current largest remaining modules.
- [x] `W67-A02` Select `home_state.py` for action split.
- [x] `W67-A03` Select `comms_email.py` for action split.
- [x] `W67-A04` Select `planner_taskplan.py` for action split.
- [x] `W67-A05` Preserve behavior and message contract compatibility.

## B) Home state split

- [x] `W67-B01` Create `home_state_smart_state.py`.
- [x] `W67-B02` Move `smart_home_state` implementation.
- [x] `W67-B03` Create `home_state_capabilities_action.py`.
- [x] `W67-B04` Move `home_assistant_capabilities` implementation.
- [x] `W67-B05` Reduce `home_state.py` to export wrapper.

## C) Email split

- [x] `W67-C01` Create `comms_email_send_action.py`.
- [x] `W67-C02` Move `email_send` implementation.
- [x] `W67-C03` Create `comms_email_summary_action.py`.
- [x] `W67-C04` Move `email_summary` implementation.
- [x] `W67-C05` Reduce `comms_email.py` to export wrapper.

## D) Task-plan split

- [x] `W67-D01` Create `planner_taskplan_create_action.py`.
- [x] `W67-D02` Move `task_plan_create` implementation.
- [x] `W67-D03` Create `planner_taskplan_list_update_actions.py`.
- [x] `W67-D04` Move `task_plan_list` implementation.
- [x] `W67-D05` Move `task_plan_update` implementation.
- [x] `W67-D06` Create `planner_taskplan_summary_next_actions.py`.
- [x] `W67-D07` Move `task_plan_summary` implementation.
- [x] `W67-D08` Move `task_plan_next` implementation.
- [x] `W67-D09` Reduce `planner_taskplan.py` to export wrapper.

## E) Boundaries and validation

- [x] `W67-E01` Extend import-boundary coverage for home state split modules.
- [x] `W67-E02` Extend import-boundary coverage for email split modules.
- [x] `W67-E03` Extend import-boundary coverage for task-plan split modules.
- [x] `W67-E04` Run focused lint on changed modules.
- [x] `W67-E05` Run targeted pytest for smart_home_state/capabilities, email, task-plan flows.
- [x] `W67-E06` Run `tests/test_import_boundaries.py`.
- [x] `W67-E07` Run full `make check`.
- [x] `W67-E08` Run full `make security-gate`.
- [x] `W67-E09` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W67-F01` Record line-count outcomes for wrapper reductions.
- [x] `W67-F02` Commit Wave 67 tranche.
- [x] `W67-F03` Push Wave 67 to origin/main.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `home_state.py`: `186 -> 8`
  - `comms_email.py`: `186 -> 8`
  - `planner_taskplan.py`: `179 -> 21`
- New extracted modules:
  - `home_state_smart_state.py`
  - `home_state_capabilities_action.py`
  - `comms_email_send_action.py`
  - `comms_email_summary_action.py`
  - `planner_taskplan_create_action.py`
  - `planner_taskplan_list_update_actions.py`
  - `planner_taskplan_summary_next_actions.py`
- Validation status:
  - Focused lint: pass.
  - Targeted pytest: `29 passed`.
  - `tests/test_import_boundaries.py`: pass.
  - `make check`: `715 passed`.
  - `make security-gate`: `715 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
