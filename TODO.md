# Jarvis TODO — Wave 47 (Integrations Ops Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 31
- Completed: 31
- Remaining: 0

---

## A) Scope and baseline

- [x] `W47-A01` Confirm Wave 46 merged and branch baseline clean.
- [x] `W47-A02` Re-profile largest remaining service-domain modules.
- [x] `W47-A03` Select `services_domains/integrations_ops.py` for decomposition.
- [x] `W47-A04` Preserve compatibility API, including private calendar helper exports.

## B) Decomposition design

- [x] `W47-B01` Define `integrations_weather.py` for weather handler.
- [x] `W47-B02` Define `integrations_webhook.py` for webhook trigger + inbound list/clear.
- [x] `W47-B03` Define `integrations_calendar.py` for calendar helpers and event queries.
- [x] `W47-B04` Define `integrations_deadletter.py` for dead-letter list/replay.
- [x] `W47-B05` Keep runtime behavior and lazy services binding unchanged.

## C) Extraction implementation

- [x] `W47-C01` Create `services_domains/integrations_weather.py`.
- [x] `W47-C02` Move `weather_lookup`.
- [x] `W47-C03` Create `services_domains/integrations_webhook.py`.
- [x] `W47-C04` Move `webhook_trigger`, `webhook_inbound_list`, `webhook_inbound_clear`.
- [x] `W47-C05` Create `services_domains/integrations_calendar.py`.
- [x] `W47-C06` Move `_calendar_fetch_events`, `_parse_calendar_window`, `calendar_events`, `calendar_next_event`.
- [x] `W47-C07` Create `services_domains/integrations_deadletter.py`.
- [x] `W47-C08` Move `dead_letter_list`, `dead_letter_replay`.

## D) Compatibility and boundaries

- [x] `W47-D01` Replace `services_domains/integrations_ops.py` with compatibility exports.
- [x] `W47-D02` Keep `services_domains/integrations.py` compatibility imports intact.
- [x] `W47-D03` Add import-boundary check for `integrations_weather`.
- [x] `W47-D04` Add import-boundary check for `integrations_webhook`.
- [x] `W47-D05` Add import-boundary check for `integrations_calendar`.
- [x] `W47-D06` Add import-boundary check for `integrations_deadletter`.

## E) Validation

- [x] `W47-E01` Run focused lint on changed integration modules + boundary tests.
- [x] `W47-E02` Run targeted pytest for integrations handlers + boundaries.
- [x] `W47-E03` Run full `make check`.
- [x] `W47-E04` Run full `make security-gate`.
- [x] `W47-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W47-F01` Capture post-split line-count outcomes.
- [x] `W47-F02` Commit and push Wave 47.

---

## Outcome snapshot (completed)

- Integrations-ops decomposition:
  - `services_domains/integrations_ops.py`: `786 -> 33` lines (compatibility exports)
  - New `services_domains/integrations_weather.py`: `149` lines
  - New `services_domains/integrations_webhook.py`: `268` lines
  - New `services_domains/integrations_calendar.py`: `240` lines
  - New `services_domains/integrations_deadletter.py`: `162` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new integrations operation modules.
- Validation status:
  - `make check`: `632 passed`
  - `make security-gate`: `632 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
