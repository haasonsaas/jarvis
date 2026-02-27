# Jarvis TODO — Wave 60 (Webhook Integration Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 23
- Completed: 23
- Remaining: 0

---

## A) Scope and baseline

- [x] `W60-A01` Re-profile next integration hotspots after Wave 59.
- [x] `W60-A02` Select `services_domains/integrations_webhook.py` for decomposition.
- [x] `W60-A03` Preserve API contract for `webhook_trigger`, `webhook_inbound_list`, and `webhook_inbound_clear`.

## B) Decomposition design

- [x] `W60-B01` Extract outbound delivery flow to `integrations_webhook_trigger.py`.
- [x] `W60-B02` Extract inbound event list/clear flow to `integrations_webhook_inbound.py`.
- [x] `W60-B03` Keep `integrations_webhook.py` as export facade.

## C) Extraction implementation

- [x] `W60-C01` Create `services_domains/integrations_webhook_trigger.py`.
- [x] `W60-C02` Move policy + allowlist + preview + delivery + dead-letter logic.
- [x] `W60-C03` Create `services_domains/integrations_webhook_inbound.py`.
- [x] `W60-C04` Move inbound list and clear handlers.
- [x] `W60-C05` Replace `integrations_webhook.py` with thin exports.

## D) Boundaries and quality

- [x] `W60-D01` Add import-boundary check for `integrations_webhook_trigger`.
- [x] `W60-D02` Add import-boundary check for `integrations_webhook_inbound`.
- [x] `W60-D03` Keep lazy service-helper access in extracted modules.

## E) Validation

- [x] `W60-E01` Run focused lint for changed webhook modules + boundary test file.
- [x] `W60-E02` Run targeted webhook tests from `test_tools_services.py`.
- [x] `W60-E03` Run `tests/test_import_boundaries.py`.
- [x] `W60-E04` Run full `make check`.
- [x] `W60-E05` Run full `make security-gate`.
- [x] `W60-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W60-F01` Capture post-split line-count outcomes.
- [x] `W60-F02` Commit Wave 60 changes.
- [x] `W60-F03` Push Wave 60 to remote.

---

## Outcome snapshot (completed)

- Webhook integration decomposition:
  - `services_domains/integrations_webhook.py`: `268 -> 11` lines (thin exports).
  - New `services_domains/integrations_webhook_trigger.py`: `233` lines.
  - New `services_domains/integrations_webhook_inbound.py`: `50` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both extracted webhook modules.
- Validation status:
  - Focused lint: pass.
  - Targeted webhook tests: pass (`4 passed`, `218 deselected`).
  - `tests/test_import_boundaries.py`: pass (`73 passed`).
  - `make check`: `662 passed`.
  - `make security-gate`: `662 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
