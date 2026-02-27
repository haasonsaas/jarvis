# Jarvis TODO — Wave 58 (Proactive Nudges Decomposition)

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

- [x] `W58-A01` Re-profile remaining `services_domains` hotspots after Wave 57.
- [x] `W58-A02` Select `services_domains/trust_proactive_nudges.py` for decomposition.
- [x] `W58-A03` Preserve proactive-assistant output contracts for anomaly and nudge actions.

## B) Decomposition design

- [x] `W58-B01` Extract anomaly scanning flow into `trust_proactive_anomaly.py`.
- [x] `W58-B02` Extract nudge decisioning flow into `trust_proactive_nudge_decision.py`.
- [x] `W58-B03` Keep `trust_proactive_nudges.py` as thin exports.

## C) Extraction implementation

- [x] `W58-C01` Create `services_domains/trust_proactive_anomaly.py`.
- [x] `W58-C02` Move `proactive_anomaly_scan` logic and payload construction.
- [x] `W58-C03` Create `services_domains/trust_proactive_nudge_decision.py`.
- [x] `W58-C04` Move candidate bucketing/capacity/dedupe logic.
- [x] `W58-C05` Move proactive counters + response payload logic.
- [x] `W58-C06` Rewrite `trust_proactive_nudges.py` to re-export handlers.

## D) Boundaries and quality

- [x] `W58-D01` Add import-boundary check for `trust_proactive_anomaly`.
- [x] `W58-D02` Add import-boundary check for `trust_proactive_nudge_decision`.
- [x] `W58-D03` Preserve runtime helper usage from `services_proactive_runtime`.

## E) Validation

- [x] `W58-E01` Run focused lint for proactive nudge modules + boundary test file.
- [x] `W58-E02` Run targeted proactive decision tests from `test_tools_services.py`.
- [x] `W58-E03` Run `tests/test_import_boundaries.py`.
- [x] `W58-E04` Run full `make check`.
- [x] `W58-E05` Run full `make security-gate`.
- [x] `W58-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W58-F01` Capture post-split line-count outcomes.
- [x] `W58-F02` Commit Wave 58 changes.
- [x] `W58-F03` Push Wave 58 to remote.

---

## Outcome snapshot (completed)

- Proactive nudge decomposition:
  - `services_domains/trust_proactive_nudges.py`: `299 -> 8` lines (thin exports).
  - New `services_domains/trust_proactive_anomaly.py`: `76` lines.
  - New `services_domains/trust_proactive_nudge_decision.py`: `234` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both extracted proactive nudge modules.
- Validation status:
  - Focused lint: pass.
  - Targeted proactive tests: pass (`5 passed`, `217 deselected`).
  - `tests/test_import_boundaries.py`: pass (`69 passed`).
  - `make check`: `658 passed`.
  - `make security-gate`: `658 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
