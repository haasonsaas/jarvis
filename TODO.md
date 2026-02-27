# Jarvis TODO — Wave 74/75 Runtime Decomposition

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 33
- Completed: 17
- Remaining: 16

---

## A) Wave 74 (completed): governance contract field split

- [x] `W74-A01` Profile next low-risk extraction target in status/governance runtime.
- [x] `W74-A02` Select `services_governance_contract.py` as split target.
- [x] `W74-A03` Preserve existing public import path: `jarvis.tools.services_governance_contract`.
- [x] `W74-A04` Keep payload shape and schema version semantics unchanged.

## B) Wave 74 implementation (completed)

- [x] `W74-B01` Create `services_governance_contract_core_fields.py`.
- [x] `W74-B02` Move core and voice/timer/reminder required-field groups.
- [x] `W74-B03` Create `services_governance_contract_operational_fields.py`.
- [x] `W74-B04` Move integrations/identity/observability/scorecard/recovery required-field groups.
- [x] `W74-B05` Create `services_governance_contract_expansion_fields.py`.
- [x] `W74-B06` Move expansion and health required-field groups.
- [x] `W74-B07` Reduce `services_governance_contract.py` to compatibility wrapper + deep-copy merge.

## C) Wave 74 validation + release (completed)

- [x] `W74-C01` Extend import-boundary coverage for new field modules.
- [x] `W74-C02` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W74-C03` Run targeted system-status contract tests.
- [x] `W74-C04` Run `make check`.
- [x] `W74-C05` Run `make security-gate`.
- [x] `W74-C06` Run `./scripts/jarvis_readiness.sh fast`.

---

## D) Wave 75 (next): services constants/bootstrap extraction

- [ ] `W75-D01` Profile top-level concentration in `src/jarvis/tools/services.py`.
- [ ] `W75-D02` Extract static defaults/constants into `services_defaults.py`.
- [ ] `W75-D03` Keep all existing constant names available via `services.py` compatibility re-exports.
- [ ] `W75-D04` Validate no behavioral change for path defaults and policy constants.
- [ ] `W75-D05` Add/extend import-boundary test coverage for new defaults module.
- [ ] `W75-D06` Run focused tests for status/governance and home/comms tools.
- [ ] `W75-D07` Run `make check`.
- [ ] `W75-D08` Run `make security-gate`.
- [ ] `W75-D09` Run `./scripts/jarvis_readiness.sh fast`.

## E) Wave 75 (next): __main__ observability snapshot dedupe

- [ ] `W75-E01` Extract observability fallback snapshot builder from `Jarvis._publish_observability_status`.
- [ ] `W75-E02` Ensure fallback structure remains contract-identical.
- [ ] `W75-E03` Add/adjust unit tests to lock fallback shape and metrics keys.
- [ ] `W75-E04` Re-run targeted `__main__` and runtime tests.
- [ ] `W75-E05` Run full quality/security/readiness gates.
- [ ] `W75-E06` Commit and push Wave 75 tranche.

---

## Outcome snapshot (latest completed wave)

- `services_governance_contract.py`: reduced to wrapper that composes field catalogs.
- New modules:
  - `services_governance_contract_core_fields.py`
  - `services_governance_contract_operational_fields.py`
  - `services_governance_contract_expansion_fields.py`
- Validation (Wave 74):
  - `uv run pytest -q tests/test_import_boundaries.py`: `168 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "system_status_contract_payload_includes_tool_policy_keys or system_status_contract_payload_includes_observability_requirements or system_status_reports_snapshot"`: `1 passed`.
  - `make check`: `757 passed`.
  - `make security-gate`: `757 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
