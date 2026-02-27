# Jarvis TODO — Wave 66 (Planner + Automation Action Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 36
- Completed: 36
- Remaining: 0

---

## A) Scope and baseline

- [x] `W66-A01` Profile current largest remaining service-domain modules.
- [x] `W66-A02` Select `home_orch_automation_apply_status.py` for action-level split.
- [x] `W66-A03` Select `planner_engine_plan_graph.py` for action-level split.
- [x] `W66-A04` Preserve action contracts and response payload compatibility.

## B) Home automation action split

- [x] `W66-B01` Create `home_orch_automation_apply_action.py`.
- [x] `W66-B02` Move `home_orch_automation_apply` implementation.
- [x] `W66-B03` Create `home_orch_automation_rollback_action.py`.
- [x] `W66-B04` Move `home_orch_automation_rollback` implementation.
- [x] `W66-B05` Create `home_orch_automation_status_action.py`.
- [x] `W66-B06` Move `home_orch_automation_status` implementation.
- [x] `W66-B07` Reduce `home_orch_automation_apply_status.py` to export wrapper.

## C) Planner plan/graph split

- [x] `W66-C01` Create `planner_engine_plan_action.py`.
- [x] `W66-C02` Move `planner_plan` implementation.
- [x] `W66-C03` Create `planner_engine_task_graph_actions.py`.
- [x] `W66-C04` Move `planner_task_graph_create` implementation.
- [x] `W66-C05` Move `planner_task_graph_update` implementation.
- [x] `W66-C06` Move `planner_task_graph_resume` implementation.
- [x] `W66-C07` Create `planner_engine_self_critique_action.py`.
- [x] `W66-C08` Move `planner_self_critique` implementation.
- [x] `W66-C09` Reduce `planner_engine_plan_graph.py` to export wrapper.

## D) Boundaries and validation

- [x] `W66-D01` Extend import-boundary coverage for new home automation action modules.
- [x] `W66-D02` Extend import-boundary coverage for new planner action modules.
- [x] `W66-D03` Run focused lint on all changed modules.
- [x] `W66-D04` Run targeted pytest for automation/planner flows.
- [x] `W66-D05` Run `tests/test_import_boundaries.py`.
- [x] `W66-D06` Run full `make check`.
- [x] `W66-D07` Run full `make security-gate`.
- [x] `W66-D08` Run `./scripts/jarvis_readiness.sh fast`.

## E) Release loop

- [x] `W66-E01` Record line-count outcomes for wrapper reductions.
- [x] `W66-E02` Commit Wave 66 tranche.
- [x] `W66-E03` Push Wave 66 to origin/main.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `home_orch_automation_apply_status.py`: `204 -> 13`
  - `planner_engine_plan_graph.py`: `195 -> 19`
- New extracted modules:
  - `home_orch_automation_apply_action.py`
  - `home_orch_automation_rollback_action.py`
  - `home_orch_automation_status_action.py`
  - `planner_engine_plan_action.py`
  - `planner_engine_task_graph_actions.py`
  - `planner_engine_self_critique_action.py`
- Validation status:
  - Focused lint: pass.
  - Targeted pytest: pass.
  - `tests/test_import_boundaries.py`: pass.
  - `make check`: `708 passed`.
  - `make security-gate`: `708 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
