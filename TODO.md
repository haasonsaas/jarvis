# Jarvis TODO — Wave 42 (Integrations + Planner Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 30
- Completed: 30
- Remaining: 0

---

## A) Scope and baseline

- [x] `W42-A01` Identify highest remaining service-domain concentration after Wave 41.
- [x] `W42-A02` Select `integrations.py` and `planner.py` for parallel decomposition.
- [x] `W42-A03` Preserve existing import/registration API surface via compatibility modules.

## B) Integrations decomposition

- [x] `W42-B01` Create `services_domains/integrations_hub.py`.
- [x] `W42-B02` Move `integration_hub` into `integrations_hub.py`.
- [x] `W42-B03` Create `services_domains/integrations_ops.py`.
- [x] `W42-B04` Move `weather_lookup` into `integrations_ops.py`.
- [x] `W42-B05` Move `webhook_trigger` into `integrations_ops.py`.
- [x] `W42-B06` Move calendar helpers (`_calendar_fetch_events`, `_parse_calendar_window`) into `integrations_ops.py`.
- [x] `W42-B07` Move `calendar_events` and `calendar_next_event` into `integrations_ops.py`.
- [x] `W42-B08` Move webhook-inbound and dead-letter handlers into `integrations_ops.py`.
- [x] `W42-B09` Replace `integrations.py` with compatibility exports, including private helper export used by `services.py`.

## C) Planner decomposition

- [x] `W42-C01` Create `services_domains/planner_engine_domain.py`.
- [x] `W42-C02` Move `planner_engine` into `planner_engine_domain.py`.
- [x] `W42-C03` Create `services_domains/planner_schedule.py`.
- [x] `W42-C04` Move timer handlers into `planner_schedule.py`.
- [x] `W42-C05` Move reminder handlers and reminder payload helpers into `planner_schedule.py`.
- [x] `W42-C06` Create `services_domains/planner_taskplan.py`.
- [x] `W42-C07` Move task-plan handlers into `planner_taskplan.py`.
- [x] `W42-C08` Replace `planner.py` with compatibility exports.

## D) Boundaries and compatibility

- [x] `W42-D01` Add import-boundary checks for `integrations_hub`.
- [x] `W42-D02` Add import-boundary checks for `integrations_ops`.
- [x] `W42-D03` Add import-boundary checks for `planner_engine_domain`.
- [x] `W42-D04` Add import-boundary checks for `planner_schedule`.
- [x] `W42-D05` Add import-boundary checks for `planner_taskplan`.
- [x] `W42-D06` Confirm existing service registration paths still resolve through compatibility modules.

## E) Validation

- [x] `W42-E01` Run focused lint for decomposed modules.
- [x] `W42-E02` Run targeted pytest selection covering integrations/planner handlers and import boundaries.
- [x] `W42-E03` Run `make check` full suite.
- [x] `W42-E04` Run `make security-gate`.
- [x] `W42-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W42-F01` Capture decomposition line-count outcomes.
- [x] `W42-F02` Commit and push Wave 42.

---

## Outcome snapshot (completed)

- Integrations decomposition:
  - `services_domains/integrations.py`: `1134 -> 31` lines (compatibility exports)
  - New `services_domains/integrations_hub.py`: `360` lines
  - New `services_domains/integrations_ops.py`: `786` lines
- Planner decomposition:
  - `services_domains/planner.py`: `1105 -> 37` lines (compatibility exports)
  - New `services_domains/planner_engine_domain.py`: `415` lines
  - New `services_domains/planner_schedule.py`: `535` lines
  - New `services_domains/planner_taskplan.py`: `179` lines
- Validation status:
  - `make check`: `613 passed`
  - `make security-gate`: `613 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
