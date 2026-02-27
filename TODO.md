# Jarvis TODO — Wave 52 (Home Orchestrator Decomposition)

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

- [x] `W52-A01` Confirm Wave 51 merged and baseline clean.
- [x] `W52-A02` Re-profile remaining large service-domain modules.
- [x] `W52-A03` Select `services_domains/home_orchestrator.py` for decomposition.
- [x] `W52-A04` Preserve `home_orchestrator` API/action behavior.

## B) Decomposition design

- [x] `W52-B01` Define `home_orch_plan_exec.py` for planning/execution/area policies.
- [x] `W52-B02` Define `home_orch_automation.py` for automation lifecycle actions.
- [x] `W52-B03` Define `home_orch_tasks.py` for task start/update/list.
- [x] `W52-B04` Keep `home_orchestrator.py` as dispatcher with policy gate.

## C) Extraction implementation

- [x] `W52-C01` Create `services_domains/home_orch_plan_exec.py`.
- [x] `W52-C02` Move `plan` and `execute` action logic.
- [x] `W52-C03` Move `area_policy_set` and `area_policy_list` action logic.
- [x] `W52-C04` Create `services_domains/home_orch_automation.py`.
- [x] `W52-C05` Move `automation_suggest` and `automation_create`.
- [x] `W52-C06` Move `automation_apply`, `automation_rollback`, and `automation_status`.
- [x] `W52-C07` Create `services_domains/home_orch_tasks.py`.
- [x] `W52-C08` Move `task_start`, `task_update`, and `task_list`.
- [x] `W52-C09` Rewrite `home_orchestrator.py` as thin dispatcher.

## D) Boundaries

- [x] `W52-D01` Add import-boundary check for `home_orch_plan_exec`.
- [x] `W52-D02` Add import-boundary check for `home_orch_automation`.
- [x] `W52-D03` Add import-boundary check for `home_orch_tasks`.

## E) Validation

- [x] `W52-E01` Run focused lint on home orchestrator modules + boundary tests.
- [x] `W52-E02` Run targeted pytest for home orchestrator action groups + boundaries.
- [x] `W52-E03` Run full `make check`.
- [x] `W52-E04` Run full `make security-gate`.
- [x] `W52-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W52-F01` Capture post-split line-count outcomes.
- [x] `W52-F02` Commit and push Wave 52.

---

## Outcome snapshot (completed)

- Home orchestrator decomposition:
  - `services_domains/home_orchestrator.py`: `398 -> 72` lines (dispatcher)
  - New `services_domains/home_orch_plan_exec.py`: `118` lines
  - New `services_domains/home_orch_automation.py`: `288` lines
  - New `services_domains/home_orch_tasks.py`: `77` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new home-orchestrator modules.
- Validation status:
  - `make check`: `645 passed`
  - `make security-gate`: `645 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
