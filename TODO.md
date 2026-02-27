# Jarvis TODO — Wave 53 (Integrations Hub Decomposition)

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

- [x] `W53-A01` Confirm baseline state and identify next large service-domain target.
- [x] `W53-A02` Re-profile `services_domains/*` file sizes after Wave 52.
- [x] `W53-A03` Select `services_domains/integrations_hub.py` for decomposition.
- [x] `W53-A04` Preserve existing `integration_hub` API/action behavior.

## B) Decomposition design

- [x] `W53-B01` Keep `integrations_hub.py` as policy gate + action dispatcher.
- [x] `W53-B02` Use `integrations_hub_calendar_notes.py` for calendar + notes actions.
- [x] `W53-B03` Use `integrations_hub_messaging.py` for messaging/commute/shopping/research.
- [x] `W53-B04` Add `integrations_hub_release_channels.py` for release-channel actions.

## C) Extraction implementation

- [x] `W53-C01` Finalize `integrations_hub_calendar_notes.py` extraction.
- [x] `W53-C02` Finalize `integrations_hub_messaging.py` extraction.
- [x] `W53-C03` Create `integrations_hub_release_channels.py`.
- [x] `W53-C04` Move `release_channel_get` action logic.
- [x] `W53-C05` Move `release_channel_set` action logic.
- [x] `W53-C06` Move `release_channel_check` action logic.
- [x] `W53-C07` Rewrite `integrations_hub.py` as thin dispatcher.

## D) Boundaries and quality

- [x] `W53-D01` Add import-boundary test for `integrations_hub_calendar_notes`.
- [x] `W53-D02` Add import-boundary test for `integrations_hub_messaging`.
- [x] `W53-D03` Add import-boundary test for `integrations_hub_release_channels`.
- [x] `W53-D04` Keep naming, typing, and helper-loading patterns consistent.

## E) Validation

- [x] `W53-E01` Run focused lint for changed integration-hub modules + boundaries.
- [x] `W53-E02` Run targeted pytest for integration-hub actions + boundaries.
- [x] `W53-E03` Run full `make check`.
- [x] `W53-E04` Run full `make security-gate`.
- [x] `W53-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W53-F01` Capture post-split line-count outcomes.
- [x] `W53-F02` Commit Wave 53 changes.
- [x] `W53-F03` Push Wave 53 to remote.

---

## Outcome snapshot (completed)

- Integrations hub decomposition:
  - `services_domains/integrations_hub.py`: reduced to action dispatcher.
  - `services_domains/integrations_hub_calendar_notes.py`: calendar + notes handlers.
  - `services_domains/integrations_hub_messaging.py`: messaging/commute/shopping/research handlers.
  - `services_domains/integrations_hub_release_channels.py`: release-channel handlers.
- Boundary enforcement:
  - Added import-boundary coverage for all three extracted integration-hub helper modules.
- Validation status:
  - Focused lint/pytest: pass.
  - `make check`: pass.
  - `make security-gate`: pass.
  - `./scripts/jarvis_readiness.sh fast`: pass.
