# Jarvis TODO — Wave 51 (Planner Engine Decomposition)

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

- [x] `W51-A01` Confirm Wave 50 merged and workspace baseline.
- [x] `W51-A02` Re-profile remaining large service-domain hotspots.
- [x] `W51-A03` Select `services_domains/planner_engine_domain.py` for decomposition.
- [x] `W51-A04` Preserve `planner_engine` tool contract and action outputs.

## B) Decomposition design

- [x] `W51-B01` Define `planner_engine_plan_graph.py` for plan/graph/self-critique actions.
- [x] `W51-B02` Define `planner_engine_deferred.py` for deferred scheduling/listing.
- [x] `W51-B03` Define `planner_engine_autonomy.py` for autonomy lifecycle actions.
- [x] `W51-B04` Keep `planner_engine_domain.py` as a dispatcher with policy gate.

## C) Extraction implementation

- [x] `W51-C01` Create `services_domains/planner_engine_plan_graph.py`.
- [x] `W51-C02` Move `plan`, `task_graph_create`, `task_graph_update`, `task_graph_resume`.
- [x] `W51-C03` Move `self_critique`.
- [x] `W51-C04` Create `services_domains/planner_engine_deferred.py`.
- [x] `W51-C05` Move `deferred_schedule` and `deferred_list`.
- [x] `W51-C06` Create `services_domains/planner_engine_autonomy.py`.
- [x] `W51-C07` Move `autonomy_schedule`, `autonomy_checkpoint`, `autonomy_cycle`, `autonomy_status`.
- [x] `W51-C08` Rewrite `planner_engine_domain.py` as thin action dispatcher.

## D) Boundaries

- [x] `W51-D01` Add import-boundary check for `planner_engine_plan_graph`.
- [x] `W51-D02` Add import-boundary check for `planner_engine_deferred`.
- [x] `W51-D03` Add import-boundary check for `planner_engine_autonomy`.

## E) Validation

- [x] `W51-E01` Run focused lint on planner-engine modules + boundary test file.
- [x] `W51-E02` Run targeted pytest for planner engine actions + import boundaries.
- [x] `W51-E03` Run full `make check`.
- [x] `W51-E04` Run full `make security-gate`.
- [x] `W51-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W51-F01` Capture post-split line-count outcomes.
- [x] `W51-F02` Commit and push Wave 51.

---

## Outcome snapshot (completed)

- Planner engine decomposition:
  - `services_domains/planner_engine_domain.py`: `415 -> 69` lines (dispatcher)
  - New `services_domains/planner_engine_plan_graph.py`: `195` lines
  - New `services_domains/planner_engine_deferred.py`: `55` lines
  - New `services_domains/planner_engine_autonomy.py`: `254` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new planner engine modules.
- Validation status:
  - `make check`: `642 passed`
  - `make security-gate`: `642 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
