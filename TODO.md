# Jarvis TODO — Wave 74/93 Runtime Decomposition

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 175
- Completed: 175
- Remaining: 0

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

## I) Wave 79 (completed): audit wrapper family extraction

- [x] `W79-I01` Profile audit wrapper block in `services.py` and select extract boundary.
- [x] `W79-I02` Create `services_audit_facade_runtime.py` for audit wrapper helpers.
- [x] `W79-I03` Preserve `services.py` compatibility names used by domain/runtime modules.
- [x] `W79-I04` Extend import-boundary coverage for new audit facade module.
- [x] `W79-I05` Run focused audit + status contract regression tests.
- [x] `W79-I06` Run `make check`.
- [x] `W79-I07` Run `make security-gate`.
- [x] `W79-I08` Run `./scripts/jarvis_readiness.sh fast`.

## J) Wave 80 (completed): identity wrapper family extraction

- [x] `W80-J01` Profile identity wrapper block in `services.py` and finalize extract boundary.
- [x] `W80-J02` Create `services_identity_facade_runtime.py` for identity wrappers.
- [x] `W80-J03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W80-J04` Extend import-boundary coverage for identity facade module.
- [x] `W80-J05` Run focused identity + policy regression tests.
- [x] `W80-J06` Run `make check`.
- [x] `W80-J07` Run `make security-gate`.
- [x] `W80-J08` Run `./scripts/jarvis_readiness.sh fast`.

## K) Wave 81 (completed): policy/guest-session wrapper extraction

- [x] `W81-K01` Profile policy/guest-session helper wrapper block in `services.py`.
- [x] `W81-K02` Create `services_policy_facade_runtime.py` for policy and guest-session wrappers.
- [x] `W81-K03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W81-K04` Extend import-boundary coverage for new policy facade module.
- [x] `W81-K05` Run focused guest-session + policy regression tests.
- [x] `W81-K06` Run `make check`.
- [x] `W81-K07` Run `make security-gate`.
- [x] `W81-K08` Run `./scripts/jarvis_readiness.sh fast`.

## L) Wave 82 (completed): recovery/dead-letter wrapper extraction

- [x] `W82-L01` Profile recovery/dead-letter wrapper block in `services.py`.
- [x] `W82-L02` Create `services_recovery_facade_runtime.py` for recovery/dead-letter wrappers.
- [x] `W82-L03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W82-L04` Extend import-boundary coverage for recovery facade module.
- [x] `W82-L05` Run focused recovery/dead-letter regression tests.
- [x] `W82-L06` Run `make check`.
- [x] `W82-L07` Run `make security-gate`.
- [x] `W82-L08` Run `./scripts/jarvis_readiness.sh fast`.

## M) Wave 83 (completed): action/history wrapper extraction

- [x] `W83-M01` Profile action-history wrapper block in `services.py`.
- [x] `W83-M02` Create `services_action_facade_runtime.py` for action-history wrappers.
- [x] `W83-M03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W83-M04` Extend import-boundary coverage for action facade module.
- [x] `W83-M05` Run focused cooldown/idempotency regression tests.
- [x] `W83-M06` Run `make check`.
- [x] `W83-M07` Run `make security-gate`.
- [x] `W83-M08` Run `./scripts/jarvis_readiness.sh fast`.

## N) Wave 84 (completed): schedule/runtime wrapper extraction

- [x] `W84-N01` Profile schedule/runtime wrapper block in `services.py`.
- [x] `W84-N02` Create `services_schedule_facade_runtime.py` for schedule/time wrappers.
- [x] `W84-N03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W84-N04` Extend import-boundary coverage for schedule facade module.
- [x] `W84-N05` Run focused timer/reminder regression tests.
- [x] `W84-N06` Run `make check`.
- [x] `W84-N07` Run `make security-gate`.
- [x] `W84-N08` Run `./scripts/jarvis_readiness.sh fast`.

## O) Wave 85 (completed): memory wrapper extraction

- [x] `W85-O01` Profile memory/planning wrapper block in `services.py`.
- [x] `W85-O02` Create `services_memory_facade_runtime.py` for memory helper wrappers.
- [x] `W85-O03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W85-O04` Extend import-boundary coverage for memory facade module.
- [x] `W85-O05` Run focused memory regression tests.
- [x] `W85-O06` Run `make check`.
- [x] `W85-O07` Run `make security-gate`.
- [x] `W85-O08` Run `./scripts/jarvis_readiness.sh fast`.

## P) Wave 86 (completed): status/scorecard wrapper extraction

- [x] `W86-P01` Profile status + scorecard wrapper block in `services.py`.
- [x] `W86-P02` Create `services_status_facade_runtime.py` for status/scorecard helper wrappers.
- [x] `W86-P03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W86-P04` Extend import-boundary coverage for status facade module.
- [x] `W86-P05` Run focused status/scorecard regression tests.
- [x] `W86-P06` Run `make check`.
- [x] `W86-P07` Run `make security-gate`.
- [x] `W86-P08` Run `./scripts/jarvis_readiness.sh fast`.

## Q) Wave 87 (completed): Home Assistant wrapper extraction

- [x] `W87-Q01` Profile Home Assistant wrapper block in `services.py`.
- [x] `W87-Q02` Create `services_ha_facade_runtime.py` for Home Assistant helper wrappers.
- [x] `W87-Q03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W87-Q04` Extend import-boundary coverage for Home Assistant facade module.
- [x] `W87-Q05` Run focused Home Assistant + home tools regression tests.
- [x] `W87-Q06` Run `make check`.
- [x] `W87-Q07` Run `make security-gate`.
- [x] `W87-Q08` Run `./scripts/jarvis_readiness.sh fast`.

## R) Wave 88 (completed): webhook/email wrapper extraction

- [x] `W88-R01` Profile webhook/email wrapper block in `services.py`.
- [x] `W88-R02` Create `services_comms_facade_runtime.py` for webhook/email helper wrappers.
- [x] `W88-R03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W88-R04` Extend import-boundary coverage for comms facade module.
- [x] `W88-R05` Run focused webhook/email/calendar regression tests.
- [x] `W88-R06` Run `make check`.
- [x] `W88-R07` Run `make security-gate`.
- [x] `W88-R08` Run `./scripts/jarvis_readiness.sh fast`.

## S) Wave 89 (completed): runtime-state wrapper extraction

- [x] `W89-S01` Profile runtime-state wrapper block in `services.py`.
- [x] `W89-S02` Create `services_state_facade_runtime.py` for runtime-state helper wrappers.
- [x] `W89-S03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W89-S04` Extend import-boundary coverage for runtime-state facade module.
- [x] `W89-S05` Run focused bind/expansion/quality-report regression tests.
- [x] `W89-S06` Run `make check`.
- [x] `W89-S07` Run `make security-gate`.
- [x] `W89-S08` Run `./scripts/jarvis_readiness.sh fast`.

## T) Wave 90 (completed): planner/automation wrapper extraction

- [x] `W90-T01` Profile planner/automation wrapper block in `services.py`.
- [x] `W90-T02` Create `services_planner_facade_runtime.py` for planner/automation helper wrappers.
- [x] `W90-T03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W90-T04` Extend import-boundary coverage for planner facade module.
- [x] `W90-T05` Run focused planner/automation/autonomy regression tests.
- [x] `W90-T06` Run `make check`.
- [x] `W90-T07` Run `make security-gate`.
- [x] `W90-T08` Run `./scripts/jarvis_readiness.sh fast`.

## U) Wave 91 (completed): coercion wrapper extraction

- [x] `W91-U01` Profile coercion wrapper block in `services.py`.
- [x] `W91-U02` Create `services_coercion_facade_runtime.py` for coercion helper wrappers.
- [x] `W91-U03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W91-U04` Extend import-boundary coverage for coercion facade module.
- [x] `W91-U05` Run focused coercion/non-finite regression tests.
- [x] `W91-U06` Run `make check`.
- [x] `W91-U07` Run `make security-gate`.
- [x] `W91-U08` Run `./scripts/jarvis_readiness.sh fast`.

## V) Wave 92 (completed): integrations/release wrapper extraction

- [x] `W92-V01` Profile integrations/release wrapper block in `services.py`.
- [x] `W92-V02` Create `services_integrations_facade_runtime.py` for integrations/release helper wrappers.
- [x] `W92-V03` Preserve `services.py` compatibility names used by runtime/domain modules.
- [x] `W92-V04` Extend import-boundary coverage for integrations facade module.
- [x] `W92-V05` Run focused integrations/release regression tests.
- [x] `W92-V06` Run `make check`.
- [x] `W92-V07` Run `make security-gate`.
- [x] `W92-V08` Run `./scripts/jarvis_readiness.sh fast`.

## W) Wave 93 (completed): __main__ wrapper dedupe + memory correction extraction

- [x] `W93-W01` Profile low-risk pass-through wrapper cluster in `src/jarvis/__main__.py`.
- [x] `W93-W02` Create `runtime_memory_correction.py` for memory correction command parsing.
- [x] `W93-W03` Replace pure pass-through `Jarvis` wrapper methods with `staticmethod` aliases.
- [x] `W93-W04` Preserve existing `Jarvis` method names and call sites used by runtime modules/tests.
- [x] `W93-W05` Run focused lifecycle/runtime control and followup-carryover regression tests.
- [x] `W93-W06` Run `make check`.
- [x] `W93-W07` Run `make security-gate`.
- [x] `W93-W08` Run `./scripts/jarvis_readiness.sh fast`.

---

## Outcome snapshot (latest completed tranche)

- New modules:
  - `services_defaults.py`
  - `runtime_observability_status.py`
  - `services_preview_facade_runtime.py`
  - `services_circuit_facade_runtime.py`
  - `services_audit_facade_runtime.py`
  - `services_identity_facade_runtime.py`
  - `services_policy_facade_runtime.py`
  - `services_recovery_facade_runtime.py`
  - `services_action_facade_runtime.py`
  - `services_schedule_facade_runtime.py`
  - `services_memory_facade_runtime.py`
  - `services_status_facade_runtime.py`
  - `services_ha_facade_runtime.py`
  - `services_comms_facade_runtime.py`
  - `services_state_facade_runtime.py`
  - `services_planner_facade_runtime.py`
  - `services_coercion_facade_runtime.py`
  - `services_integrations_facade_runtime.py`
  - `runtime_memory_correction.py`
- Compatibility preservation:
  - `services.py` now re-exports defaults/constants via `_services_defaults` alias.
  - Mutable bootstrap defaults (`_proactive_state`, `_privacy_posture`, `_motion_safety_envelope`, `_release_channel_state`) now initialize from factory helpers.
  - `services.re` export preserved for domain-module compatibility.
  - `Jarvis._publish_observability_status` now uses a shared default snapshot helper for both disabled-observability and exception fallback paths.
  - Operator auth mode normalization and risk classification are now shared helpers used by both runtime status payloads and startup summary lines.
  - Plan-preview wrapper family moved behind `services_preview_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Circuit-breaker wrapper family moved behind `services_circuit_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Audit wrapper family moved behind `services_audit_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Identity wrapper family moved behind `services_identity_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Policy + guest-session wrapper family moved behind `services_policy_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Recovery + dead-letter wrapper family moved behind `services_recovery_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Action-history wrapper family moved behind `services_action_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Schedule/timer/reminder wrapper family moved behind `services_schedule_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Memory/planning wrapper family moved behind `services_memory_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Status/scorecard wrapper family moved behind `services_status_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Home Assistant wrapper family moved behind `services_ha_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Webhook/email wrapper family moved behind `services_comms_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Runtime-state wrapper family moved behind `services_state_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Planner/automation wrapper family moved behind `services_planner_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Coercion wrapper family moved behind `services_coercion_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - Integrations/release wrapper family moved behind `services_integrations_facade_runtime.py` with `services.py` compatibility aliases maintained.
  - `Jarvis` pass-through wrappers for control/intent/telemetry helpers now use direct `staticmethod` aliases where behavior is identical.
  - Memory correction parsing logic moved from `Jarvis._parse_memory_correction_command` body into `runtime_memory_correction.py`.
- Validation (Wave 75D/E):
  - `uv run pytest -q tests/test_import_boundaries.py`: `177 passed`.
  - `uv run pytest -q tests/test_runtime_operator_status.py tests/test_main_lifecycle.py -k "operator_auth or startup_summary_lines_include_core_status"`: `8 passed`.
  - `uv run pytest -q tests/test_main_lifecycle.py -k "publish_observability_status"`: `2 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "preview_only_returns_plan_preview or strict_preview_ack_requires_token_then_executes or plan_preview"`: `2 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "weather_circuit_breaker_blocks_requests_and_surfaces_status or system_status_reports_snapshot or integration_circuit_breaker_required"`: `2 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "audit"`: `17 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "identity_profile_deny_blocks_webhook_and_records_requester or identity_high_risk_webhook_requires_approval_code or identity_high_risk_webhook_allows_code_or_trusted_approval or identity_guest_session_capability_enforced"`: `4 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "reminder_notify_due_defers_inside_quiet_window or proactive_nudge_decision_adaptive_quiet_window or identity_guest_session_capability_enforced"`: `3 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "dead_letter_queue_captures_webhook_failure_and_replays or recovery_journal_begin_finish_status or bind_reconciles_interrupted_recovery_entries"`: `3 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "retry_backoff_delay_bounds_and_jitter or smart_home_idempotent_turn_on_short_circuits"`: `2 passed`.
  - `uv run pytest -q tests/test_main_lifecycle.py tests/test_main_audio.py tests/test_runtime_state.py`: `54 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "timer or reminder"`: `13 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_memory.py tests/test_tools_services.py -k "memory_"`: `34 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py tests/test_main_lifecycle.py -k "system_status or scorecard or observability or identity_status or voice_attention"`: `12 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py -k "home_assistant or smart_home_state or media_control or calendar_events or calendar_next_event or home_orchestrator"`: `43 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py -k "webhook or email_send or calendar_events or calendar_next_event"`: `25 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py tests/test_main_lifecycle.py -k "bind or expansion or quality_report or release_channel"`: `11 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py -k "planner_engine or home_automation or autonomy or task_plan or deferred_action"`: `24 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py -k "non_finite or bool_sensitivity or include_sensitive or memory_search_non_finite_include_sensitive_uses_default_false"`: `5 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py tests/test_tools_services.py -k "release_channel or quality_report_artifact or capture_note or note_capture"`: `2 passed`.
  - `uv run pytest -q tests/test_main_lifecycle.py tests/test_runtime_voice_profile.py tests/test_runtime_state.py -k "parse_memory_correction_command or classify_user_intent or looks_like_user_correction or parse_control_bool or parse_control_choice or followup_carryover"`: `12 passed`.
  - `make check`: `784 passed`.
  - `make security-gate`: `784 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
