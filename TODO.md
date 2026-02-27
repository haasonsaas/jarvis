# Jarvis TODO — Wave 63 (Runtime Decomposition Sweep III)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 52
- Completed: 52
- Remaining: 0

---

## A) Scope and baseline

- [x] `W63-A01` Capture next hotspot set after Wave 62.
- [x] `W63-A02` Select decomposition targets focused on runtime concentration and maintainability.
- [x] `W63-A03` Include `trust_proactive_nudge_decision.py` in scope.
- [x] `W63-A04` Include `planner_timers.py` in scope.
- [x] `W63-A05` Include `planner_reminders_crud.py` in scope.
- [x] `W63-A06` Include `governance_quality.py` in scope.
- [x] `W63-A07` Preserve action contracts and response shape compatibility.
- [x] `W63-A08` Preserve state/counter semantics for proactive decisioning.

## B) Proactive nudge decision split

- [x] `W63-B01` Create `trust_proactive_nudge_decision_classify.py`.
- [x] `W63-B02` Move candidate/context parsing and classification into classifier module.
- [x] `W63-B03` Keep dedupe bucket fallback and context downgrade behavior unchanged.
- [x] `W63-B04` Create `trust_proactive_nudge_decision_finalize.py`.
- [x] `W63-B05` Move dispatch-capacity trimming and overflow handling into finalizer.
- [x] `W63-B06` Move recent-dispatch writeback and pruning into finalizer.
- [x] `W63-B07` Move payload/counters emission into finalizer.
- [x] `W63-B08` Reduce `trust_proactive_nudge_decision.py` to orchestration wrapper.

## C) Timer split

- [x] `W63-C01` Create `planner_timers_create.py`.
- [x] `W63-C02` Move `timer_create` into create module.
- [x] `W63-C03` Create `planner_timers_list_cancel.py`.
- [x] `W63-C04` Move `timer_list` into list/cancel module.
- [x] `W63-C05` Move `timer_cancel` into list/cancel module.
- [x] `W63-C06` Reduce `planner_timers.py` to export wrapper.

## D) Reminder CRUD split

- [x] `W63-D01` Create `planner_reminders_create.py`.
- [x] `W63-D02` Move `reminder_create` into create module.
- [x] `W63-D03` Create `planner_reminders_list_complete.py`.
- [x] `W63-D04` Move reminder list payload helper into list/complete module.
- [x] `W63-D05` Move `reminder_list` into list/complete module.
- [x] `W63-D06` Move `reminder_complete` into list/complete module.
- [x] `W63-D07` Reduce `planner_reminders_crud.py` to export wrapper.

## E) Governance quality split

- [x] `W63-E01` Create `governance_quality_evaluator_actions.py`.
- [x] `W63-E02` Move `weekly_report` action logic.
- [x] `W63-E03` Move `dataset_run` action logic.
- [x] `W63-E04` Move `reports_list` action logic.
- [x] `W63-E05` Create `governance_quality_embodiment_actions.py`.
- [x] `W63-E06` Move `expression_library` action logic.
- [x] `W63-E07` Move `gaze_calibrate` action logic.
- [x] `W63-E08` Move `gesture_profile` action logic.
- [x] `W63-E09` Move `privacy_posture` action logic.
- [x] `W63-E10` Move `safety_envelope` action logic.
- [x] `W63-E11` Move `status` action logic.
- [x] `W63-E12` Reduce `governance_quality.py` to dispatch wrapper.

## F) Boundaries and compatibility

- [x] `W63-F01` Extend import-boundary coverage for proactive classifier/finalizer modules.
- [x] `W63-F02` Extend import-boundary coverage for timer split modules.
- [x] `W63-F03` Extend import-boundary coverage for reminder split modules.
- [x] `W63-F04` Extend import-boundary coverage for quality/embodiment action modules.
- [x] `W63-F05` Run focused lint for all changed modules.
- [x] `W63-F06` Run targeted pytest for proactive/timer/reminder/quality behaviors.
- [x] `W63-F07` Run `tests/test_import_boundaries.py`.

## G) Full verification gates

- [x] `W63-G01` Run full `make check`.
- [x] `W63-G02` Run full `make security-gate`.
- [x] `W63-G03` Run `./scripts/jarvis_readiness.sh fast`.

## H) Release loop

- [x] `W63-H01` Record line-count reductions and extracted modules.
- [x] `W63-H02` Commit Wave 63 tranche.
- [x] `W63-H03` Push Wave 63 to origin/main.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `trust_proactive_nudge_decision.py`: `234 -> 72`
  - `planner_timers.py`: `201 -> 11`
  - `planner_reminders_crud.py`: `197 -> 11`
  - `governance_quality.py`: `201 -> 79`
- New extracted modules:
  - `trust_proactive_nudge_decision_classify.py`
  - `trust_proactive_nudge_decision_finalize.py`
  - `planner_timers_create.py`
  - `planner_timers_list_cancel.py`
  - `planner_reminders_create.py`
  - `planner_reminders_list_complete.py`
  - `governance_quality_evaluator_actions.py`
  - `governance_quality_embodiment_actions.py`
- Validation status:
  - Focused lint: pass.
  - Focused pytest: `11 passed` (targeted selection).
  - `tests/test_import_boundaries.py`: pass.
  - `make check`: `692 passed`.
  - `make security-gate`: `692 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
