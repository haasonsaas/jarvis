# Jarvis TODO — Wave 50 (Proactive Trust Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 26
- Completed: 26
- Remaining: 0

---

## A) Scope and baseline

- [x] `W50-A01` Confirm Wave 49 merged and tree is clean before edits.
- [x] `W50-A02` Re-profile remaining largest service-domain modules.
- [x] `W50-A03` Select `services_domains/trust.py` for decomposition.
- [x] `W50-A04` Preserve `proactive_assistant` API behavior and action contract.

## B) Decomposition design

- [x] `W50-B01` Define `trust_proactive_briefing.py` for `briefing` + `event_digest`.
- [x] `W50-B02` Define `trust_proactive_nudges.py` for `anomaly_scan` + `nudge_decision`.
- [x] `W50-B03` Define `trust_proactive_followthrough.py` for `routine_suggestions` + `follow_through`.
- [x] `W50-B04` Keep `trust.py` as thin dispatcher and policy gate.

## C) Extraction implementation

- [x] `W50-C01` Create `services_domains/trust_proactive_briefing.py`.
- [x] `W50-C02` Move `briefing` action logic.
- [x] `W50-C03` Move `event_digest` action logic.
- [x] `W50-C04` Create `services_domains/trust_proactive_nudges.py`.
- [x] `W50-C05` Move `anomaly_scan` action logic.
- [x] `W50-C06` Move `nudge_decision` action logic and runtime dedupe helpers.
- [x] `W50-C07` Create `services_domains/trust_proactive_followthrough.py`.
- [x] `W50-C08` Move `routine_suggestions` action logic.
- [x] `W50-C09` Move `follow_through` action logic.
- [x] `W50-C10` Rewrite `trust.py` as a small action dispatcher.

## D) Boundaries

- [x] `W50-D01` Add import-boundary check for `trust_proactive_briefing`.
- [x] `W50-D02` Add import-boundary check for `trust_proactive_nudges`.
- [x] `W50-D03` Add import-boundary check for `trust_proactive_followthrough`.

## E) Validation

- [x] `W50-E01` Run focused lint on touched trust/proactive modules + boundary file.
- [x] `W50-E02` Run targeted pytest for proactive assistant actions + boundaries.
- [x] `W50-E03` Run full `make check`.
- [x] `W50-E04` Run full `make security-gate`.
- [x] `W50-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W50-F01` Capture post-split line-count outcomes.
- [x] `W50-F02` Commit and push Wave 50.

---

## Outcome snapshot (completed)

- Proactive trust decomposition:
  - `services_domains/trust.py`: `419 -> 56` lines (dispatcher)
  - New `services_domains/trust_proactive_briefing.py`: `101` lines
  - New `services_domains/trust_proactive_nudges.py`: `299` lines
  - New `services_domains/trust_proactive_followthrough.py`: `89` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new proactive trust modules.
- Validation status:
  - `make check`: `639 passed`
  - `make security-gate`: `639 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
