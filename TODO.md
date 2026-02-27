# Jarvis TODO — Wave 68 (Status/Governance/Recovery Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 35
- Completed: 35
- Remaining: 0

---

## A) Scope and baseline

- [x] `W68-A01` Profile largest remaining runtime hotspots in `src/jarvis/tools`.
- [x] `W68-A02` Select `services_status_runtime.py` for split.
- [x] `W68-A03` Select `services_governance_runtime.py` for split.
- [x] `W68-A04` Select `services_recovery_runtime.py` for split.
- [x] `W68-A05` Keep import API stable for `services.py` callers.

## B) Status runtime split

- [x] `W68-B01` Create `services_status_snapshots_runtime.py`.
- [x] `W68-B02` Move integration/identity/voice snapshot helpers.
- [x] `W68-B03` Move observability/skills/expansion snapshot helpers.
- [x] `W68-B04` Move `health_rollup` helper.
- [x] `W68-B05` Create `services_status_scorecard_runtime.py`.
- [x] `W68-B06` Move scorecard helpers (`score_label`, row extraction, p95, scorecard payload).
- [x] `W68-B07` Reduce `services_status_runtime.py` to compatibility wrapper.

## C) Governance runtime split

- [x] `W68-C01` Create `services_governance_status_payload.py`.
- [x] `W68-C02` Move tool-policy/scorecard-context payload helpers.
- [x] `W68-C03` Create `services_governance_contract.py`.
- [x] `W68-C04` Move system-status contract field map + payload helper.
- [x] `W68-C05` Reduce `services_governance_runtime.py` to compatibility wrapper.

## D) Recovery runtime split

- [x] `W68-D01` Create `services_recovery_journal_runtime.py`.
- [x] `W68-D02` Move journal read/write/start/finish helpers.
- [x] `W68-D03` Move `RecoveryOperation` context manager and reconcile/status helpers.
- [x] `W68-D04` Create `services_dead_letter_runtime.py`.
- [x] `W68-D05` Move dead-letter read/write/enqueue/status helpers.
- [x] `W68-D06` Create `services_recovery_response_runtime.py`.
- [x] `W68-D07` Move tool-response text/success evaluators.
- [x] `W68-D08` Reduce `services_recovery_runtime.py` to compatibility wrapper.

## E) Boundaries and verification

- [x] `W68-E01` Extend import-boundary coverage for new status runtime modules.
- [x] `W68-E02` Extend import-boundary coverage for new governance runtime modules.
- [x] `W68-E03` Extend import-boundary coverage for new recovery runtime modules.
- [x] `W68-E04` Run focused lint for changed runtime files.
- [x] `W68-E05` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W68-E06` Run targeted status/recovery governance tool tests.
- [x] `W68-E07` Run full `make check`.
- [x] `W68-E08` Run full `make security-gate`.
- [x] `W68-E09` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W68-F01` Record wrapper reductions and extracted module counts.
- [x] `W68-F02` Commit Wave 68 tranche.
- [x] `W68-F03` Push Wave 68 to `origin/main`.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `services_status_runtime.py`: `628 -> 33`
  - `services_governance_runtime.py`: `496 -> 17`
  - `services_recovery_runtime.py`: `419 -> 45`
- New extracted modules:
  - `services_status_snapshots_runtime.py`
  - `services_status_scorecard_runtime.py`
  - `services_governance_status_payload.py`
  - `services_governance_contract.py`
  - `services_recovery_journal_runtime.py`
  - `services_dead_letter_runtime.py`
  - `services_recovery_response_runtime.py`
- Validation status:
  - `uv run pytest -q tests/test_import_boundaries.py`: `135 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "system_status or jarvis_scorecard or dead_letter or recovery_journal"`: `9 passed`.
  - `make check`: `724 passed`.
  - `make security-gate`: `724 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
