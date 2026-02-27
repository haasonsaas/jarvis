# Jarvis TODO — Wave 74/79 Runtime Decomposition

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 63
- Completed: 55
- Remaining: 8

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

## D) Wave 75 (completed): services constants/bootstrap extraction

- [x] `W75-D01` Profile top-level concentration in `src/jarvis/tools/services.py`.
- [x] `W75-D02` Extract static defaults/constants into `services_defaults.py`.
- [x] `W75-D03` Keep all existing constant names available via `services.py` compatibility re-exports.
- [x] `W75-D04` Validate no behavioral change for path defaults and policy constants.
- [x] `W75-D05` Add/extend import-boundary test coverage for new defaults module.
- [x] `W75-D06` Run focused tests for status/governance and home/comms tools.
- [x] `W75-D07` Run `make check`.
- [x] `W75-D08` Run `make security-gate`.
- [x] `W75-D09` Run `./scripts/jarvis_readiness.sh fast`.

## E) Wave 75 (completed): __main__ observability snapshot dedupe

- [x] `W75-E01` Extract observability fallback snapshot builder from `Jarvis._publish_observability_status`.
- [x] `W75-E02` Ensure fallback structure remains contract-identical.
- [x] `W75-E03` Add/adjust unit tests to lock fallback shape and metrics keys.
- [x] `W75-E04` Re-run targeted `__main__` and runtime tests.
- [x] `W75-E05` Run full quality/security/readiness gates.
- [x] `W75-E06` Commit and push Wave 75 tranche.

## F) Wave 76 (completed): operator auth normalization/risk dedupe

- [x] `W76-F01` Identify duplicate operator auth mode normalization logic across runtime modules.
- [x] `W76-F02` Identify duplicate operator auth risk classification logic.
- [x] `W76-F03` Extract shared helpers into `runtime_operator_status.py`.
- [x] `W76-F04` Rewire `Jarvis._startup_summary_lines` to shared helpers.
- [x] `W76-F05` Add unit coverage for helper behavior matrix.
- [x] `W76-F06` Run full quality/security/readiness gates.

## G) Wave 77 (completed): services wrapper concentration reduction

- [x] `W77-G01` Profile largest contiguous wrapper region in `src/jarvis/tools/services.py`.
- [x] `W77-G02` Select one wrapper family (audit/identity/preview/circuit/recovery) for extraction.
- [x] `W77-G03` Preserve `services.py` compatibility exports consumed by domain modules.
- [x] `W77-G04` Add/extend import-boundary coverage for any new extraction module(s).
- [x] `W77-G05` Add focused regression tests around extracted wrapper family.
- [x] `W77-G06` Run `make check`.
- [x] `W77-G07` Run `make security-gate`.
- [x] `W77-G08` Run `./scripts/jarvis_readiness.sh fast`.

## H) Wave 78 (completed): circuit wrapper concentration reduction

- [x] `W78-H01` Select circuit-breaker wrapper family from `services.py`.
- [x] `W78-H02` Extract circuit wrappers into `services_circuit_facade_runtime.py`.
- [x] `W78-H03` Preserve existing `services.py` compatibility aliases for circuit helpers.
- [x] `W78-H04` Add import-boundary coverage for the new circuit facade module.
- [x] `W78-H05` Run focused circuit/regression tests.
- [x] `W78-H06` Run `make check`.
- [x] `W78-H07` Run `make security-gate`.
- [x] `W78-H08` Run `./scripts/jarvis_readiness.sh fast`.

## I) Wave 79 (next): audit wrapper family extraction

- [ ] `W79-I01` Profile audit wrapper block in `services.py` and select extract boundary.
- [ ] `W79-I02` Create `services_audit_facade_runtime.py` for audit wrapper helpers.
- [ ] `W79-I03` Preserve `services.py` compatibility names used by domain/runtime modules.
- [ ] `W79-I04` Extend import-boundary coverage for new audit facade module.
- [ ] `W79-I05` Run focused audit + status contract regression tests.
- [ ] `W79-I06` Run `make check`.
- [ ] `W79-I07` Run `make security-gate`.
- [ ] `W79-I08` Run `./scripts/jarvis_readiness.sh fast`.

---

## Outcome snapshot (latest completed tranche)

- New modules:
  - `services_defaults.py`
  - `runtime_observability_status.py`
  - `services_preview_facade_runtime.py`
  - `services_circuit_facade_runtime.py`
- Compatibility preservation:
  - `services.py` now re-exports defaults/constants via `_services_defaults` alias.
  - Mutable bootstrap defaults (`_proactive_state`, `_privacy_posture`, `_motion_safety_envelope`, `_release_channel_state`) now initialize from factory helpers.
  - `services.re` export preserved for domain-module compatibility.
  - `Jarvis._publish_observability_status` now uses a shared default snapshot helper for both disabled-observability and exception fallback paths.
  - Operator auth mode normalization and risk classification are now shared helpers used by both runtime status payloads and startup summary lines.
  - Plan-preview wrapper family moved behind `services_preview_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Circuit-breaker wrapper family moved behind `services_circuit_facade_runtime.py` with `services.py` compatibility aliases maintained.
- Validation (Wave 75D/E):
  - `uv run pytest -q tests/test_import_boundaries.py`: `172 passed`.
  - `uv run pytest -q tests/test_runtime_operator_status.py tests/test_main_lifecycle.py -k "operator_auth or startup_summary_lines_include_core_status"`: `8 passed`.
  - `uv run pytest -q tests/test_main_lifecycle.py -k "publish_observability_status"`: `2 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "preview_only_returns_plan_preview or strict_preview_ack_requires_token_then_executes or plan_preview"`: `2 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "weather_circuit_breaker_blocks_requests_and_surfaces_status or system_status_reports_snapshot or integration_circuit_breaker_required"`: `2 passed`.
  - `uv run pytest -q tests/test_main_lifecycle.py tests/test_main_audio.py tests/test_runtime_state.py`: `54 passed`.
  - `make check`: `770 passed`.
  - `make security-gate`: `770 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
