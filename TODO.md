# Jarvis TODO — Wave 49 (Comms Notification Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 25
- Completed: 25
- Remaining: 0

---

## A) Scope and baseline

- [x] `W49-A01` Confirm Wave 48 merged locally and baseline status.
- [x] `W49-A02` Re-profile largest domain modules after planner split.
- [x] `W49-A03` Select `services_domains/comms_notifications.py` for further decomposition.
- [x] `W49-A04` Preserve existing compatibility import surface.

## B) Decomposition design

- [x] `W49-B01` Define `comms_notify_webhooks.py` for Slack/Discord handlers.
- [x] `W49-B02` Define `comms_notify_pushover.py` for Pushover handler.
- [x] `W49-B03` Keep lazy `services` binding and existing behavior unchanged.

## C) Extraction implementation

- [x] `W49-C01` Create `services_domains/comms_notify_webhooks.py`.
- [x] `W49-C02` Move `slack_notify` and `discord_notify`.
- [x] `W49-C03` Create `services_domains/comms_notify_pushover.py`.
- [x] `W49-C04` Move `pushover_notify`.
- [x] `W49-C05` Replace `services_domains/comms_notifications.py` with compatibility exports.

## D) Boundaries

- [x] `W49-D01` Add import-boundary check for `comms_notify_webhooks`.
- [x] `W49-D02` Add import-boundary check for `comms_notify_pushover`.

## E) Validation

- [x] `W49-E01` Run focused lint on touched comms notification modules + boundary test file.
- [x] `W49-E02` Run targeted pytest for Slack/Discord/Pushover handlers + boundaries.
- [x] `W49-E03` Run full `make check`.
- [x] `W49-E04` Run full `make security-gate`.
- [x] `W49-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W49-F01` Capture post-split line-count outcomes.
- [x] `W49-F02` Commit and push Wave 49.

---

## Outcome snapshot (completed)

- Comms notification decomposition:
  - `services_domains/comms_notifications.py`: `415 -> 15` lines (compatibility exports)
  - New `services_domains/comms_notify_webhooks.py`: `257` lines
  - New `services_domains/comms_notify_pushover.py`: `169` lines
- Boundary enforcement:
  - Added import-boundary coverage for new comms notification modules.
- Validation status:
  - `make check`: `636 passed`
  - `make security-gate`: `636 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
