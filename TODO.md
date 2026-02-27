# Jarvis TODO — Wave 74/101 Runtime Decomposition

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 239
- Completed: 239
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

## X) Wave 94 (completed): __main__ STT fallback extraction

- [x] `W94-X01` Profile `Jarvis._transcribe_with_fallback` extraction boundary.
- [x] `W94-X02` Extract STT fallback orchestration into `runtime_telemetry.py`.
- [x] `W94-X03` Keep `Jarvis._transcribe_with_fallback` method contract unchanged.
- [x] `W94-X04` Preserve telemetry + observability side-effects (`fallback_responses`, `stt_fallback` event).
- [x] `W94-X05` Run focused audio/lifecycle/runtime-state regression tests.
- [x] `W94-X06` Run `make check`.
- [x] `W94-X07` Run `make security-gate`.
- [x] `W94-X08` Run `./scripts/jarvis_readiness.sh fast`.

## Y) Wave 95 (completed): __main__ conversation trace extraction

- [x] `W95-Y01` Profile conversation trace/episodic snapshot extraction boundary in `src/jarvis/__main__.py`.
- [x] `W95-Y02` Create `runtime_conversation_trace.py` for trace + episodic runtime helpers.
- [x] `W95-Y03` Rewire `Jarvis._record_conversation_trace` and `_record_episodic_snapshot` to runtime helpers.
- [x] `W95-Y04` Rewire operator trace providers to runtime helpers.
- [x] `W95-Y05` Extend import-boundary coverage for new runtime helper modules.
- [x] `W95-Y06` Run focused lifecycle/operator/audio/import-boundary regression tests.
- [x] `W95-Y07` Run `make check`.
- [x] `W95-Y08` Run `make security-gate`.

## Z) Wave 96 (completed): reliability soak execution hardening

- [x] `W96-Z01` Add repeatable fast-soak reliability script entrypoint (`scripts/test_soak_reliability.sh`).
- [x] `W96-Z02` Validate script input guards for repeat-cycle argument.
- [x] `W96-Z03` Add `make test-soak-reliability` target.
- [x] `W96-Z04` Execute multi-cycle soak run (`repeat=2`) and capture artifact.
- [x] `W96-Z05` Verify soak acceptance/phase accounting in generated JSON artifact.
- [x] `W96-Z06` Re-run full `make check` after soak-target changes.
- [x] `W96-Z07` Keep quality/security/readiness baselines green.
- [x] `W96-Z08` Update TODO and release notes with reliability soak status.

## AA) Wave 97 (completed): __main__ operator-server lifecycle extraction

- [x] `W97-AA01` Profile operator-server provider/lifecycle extraction boundary in `src/jarvis/__main__.py`.
- [x] `W97-AA02` Create `runtime_operator_server.py` for startup diagnostics, metrics/events providers, and server lifecycle helpers.
- [x] `W97-AA03` Rewire `Jarvis` operator provider methods to runtime helpers.
- [x] `W97-AA04` Rewire `Jarvis._start_operator_server`/`_stop_operator_server` to runtime helpers while preserving call contracts.
- [x] `W97-AA05` Add unit coverage for runtime operator-server helper behavior.
- [x] `W97-AA06` Extend import-boundary coverage for new runtime helper module.
- [x] `W97-AA07` Run full quality/security/readiness gates.
- [x] `W97-AA08` Update TODO + tranche snapshot.

## AB) Wave 98 (completed): __main__ audio-output runtime extraction

- [x] `W98-AB01` Profile `Jarvis` audio output + TTS loop helper concentration in `src/jarvis/__main__.py`.
- [x] `W98-AB02` Create `runtime_audio_output.py` for flush/play/queue-clear/TTS-loop helpers.
- [x] `W98-AB03` Rewire `Jarvis._flush_output`, `_play_audio_chunk`, `_tts_loop`, and `_clear_tts_queue` to runtime helpers.
- [x] `W98-AB04` Preserve existing barge-in, fallback text-only, telemetry, and observability side-effects.
- [x] `W98-AB05` Add focused unit tests for runtime audio-output helpers.
- [x] `W98-AB06` Extend import-boundary coverage for `runtime_audio_output`.
- [x] `W98-AB07` Run full quality/security/readiness gates.
- [x] `W98-AB08` Update TODO + tranche snapshot.

## AC) Wave 99 (completed): __main__ lifecycle runtime extraction

- [x] `W99-AC01` Profile startup/shutdown concentration in `Jarvis.start`/`Jarvis.stop`.
- [x] `W99-AC02` Create `runtime_lifecycle.py` for startup/shutdown orchestration helpers.
- [x] `W99-AC03` Rewire `Jarvis.start`/`Jarvis.stop` to runtime lifecycle helpers.
- [x] `W99-AC04` Keep sounddevice guard and vision tracker lazy-construction behavior unchanged.
- [x] `W99-AC05` Add focused unit coverage for runtime lifecycle helper paths.
- [x] `W99-AC06` Extend import-boundary coverage for `runtime_lifecycle`.
- [x] `W99-AC07` Run full quality/security/readiness gates.
- [x] `W99-AC08` Update TODO + tranche snapshot.

## AD) Wave 100 (completed): turn-confidence and confirmation heuristic extraction

- [x] `W100-AD01` Profile turn-taking, attention-confidence, and confirmation/repair heuristics in `src/jarvis/__main__.py`.
- [x] `W100-AD02` Extend `runtime_turn.py` with shared helpers for attention confidence and turn-taking decisions.
- [x] `W100-AD03` Extend `runtime_turn.py` with shared helpers for STT repair and confirmation gating heuristics.
- [x] `W100-AD04` Rewire `Jarvis._compute_turn_taking`, `_attention_confidence`, `_requires_stt_repair`, and `_requires_confirmation` to runtime-turn helpers.
- [x] `W100-AD05` Add focused unit coverage in `tests/test_runtime_turn.py`.
- [x] `W100-AD06` Extend import-boundary coverage for `runtime_turn`.
- [x] `W100-AD07` Run full quality/security/readiness gates.
- [x] `W100-AD08` Update TODO + tranche snapshot.

## AE) Wave 101 (completed): startup summary extraction into runtime_startup

- [x] `W101-AE01` Profile `_startup_summary_lines` concentration in `src/jarvis/__main__.py`.
- [x] `W101-AE02` Extend `runtime_startup.py` with `startup_summary_lines` helper.
- [x] `W101-AE03` Rewire `Jarvis._startup_summary_lines` to runtime helper without changing output contract.
- [x] `W101-AE04` Keep operator auth normalization/risk behavior and tool-taxonomy counters unchanged.
- [x] `W101-AE05` Extend `tests/test_runtime_startup.py` with startup-summary coverage.
- [x] `W101-AE06` Run focused startup/lifecycle/runtime helper regression tests.
- [x] `W101-AE07` Run full quality/security/readiness gates.
- [x] `W101-AE08` Update TODO + tranche snapshot.

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
  - `runtime_conversation_trace.py`
  - `runtime_operator_server.py`
  - `runtime_audio_output.py`
  - `runtime_lifecycle.py`
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
  - STT fallback orchestration moved from `Jarvis._transcribe_with_fallback` body into `runtime_telemetry.transcribe_with_fallback`.
  - Conversation trace + episodic snapshot logic moved from `Jarvis` method bodies into `runtime_conversation_trace.py`.
  - Added repeatable reliability soak entrypoint `scripts/test_soak_reliability.sh` and `make test-soak-reliability` target.
  - Operator-server provider/lifecycle logic moved from `Jarvis` method bodies into `runtime_operator_server.py`.
  - Audio output + TTS stream loop logic moved from `Jarvis` method bodies into `runtime_audio_output.py`.
  - Startup/shutdown orchestration moved from `Jarvis.start`/`Jarvis.stop` into `runtime_lifecycle.py`.
  - Turn-taking, attention-confidence, STT-repair, and confirmation heuristics moved from `Jarvis` method bodies into `runtime_turn.py`.
  - Startup summary line composition moved from `Jarvis._startup_summary_lines` into `runtime_startup.startup_summary_lines`.
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
  - `uv run pytest -q tests/test_main_audio.py tests/test_main_lifecycle.py tests/test_runtime_voice_profile.py tests/test_runtime_state.py -k "transcribe_with_fallback or parse_memory_correction_command or parse_control_bool or parse_control_choice or followup_carryover"`: `11 passed`.
  - `uv run pytest -q tests/test_main_lifecycle.py tests/test_runtime_operator_status.py tests/test_main_audio.py tests/test_import_boundaries.py`: `248 passed`.
  - `uv run pytest -q tests/test_runtime_operator_server.py tests/test_main_lifecycle.py tests/test_runtime_operator_status.py tests/test_import_boundaries.py -k "operator_server or operator_metrics_provider or operator_events_provider or startup_diagnostics_provider"`: `5 passed`.
  - `uv run pytest -q tests/test_runtime_audio_output.py tests/test_main_audio.py tests/test_import_boundaries.py -k "runtime_audio_output or tts_loop or play_audio_chunk or clear_tts_queue or import_boundary"`: `198 passed, 6 deselected`.
  - `uv run pytest -q tests/test_main_lifecycle.py tests/test_main_audio.py tests/test_runtime_operator_server.py tests/test_import_boundaries.py`: `244 passed`.
  - `uv run pytest -q tests/test_runtime_lifecycle.py tests/test_main_lifecycle.py tests/test_main_audio.py tests/test_import_boundaries.py -k "runtime_lifecycle or start or stop or sounddevice or import_boundary"`: `201 passed, 44 deselected`.
  - `uv run pytest -q tests/test_main_lifecycle.py tests/test_runtime_operator_server.py tests/test_runtime_audio_output.py tests/test_import_boundaries.py`: `243 passed`.
  - `uv run pytest -q tests/test_runtime_turn.py tests/test_main_lifecycle.py tests/test_main_audio.py tests/test_import_boundaries.py -k "runtime_turn or requires_stt_repair or requires_confirmation or compute_turn_taking or attention_confidence or import_boundary"`: `200 passed, 47 deselected`.
  - `uv run pytest -q tests/test_runtime_lifecycle.py tests/test_runtime_audio_output.py tests/test_main_lifecycle.py tests/test_import_boundaries.py`: `244 passed`.
  - `uv run pytest -q tests/test_runtime_startup.py tests/test_main_lifecycle.py tests/test_import_boundaries.py -k "startup_summary_lines or runtime_startup or startup_blockers or operator_auth or import_boundary"`: `197 passed, 41 deselected`.
  - `uv run pytest -q tests/test_runtime_lifecycle.py tests/test_runtime_audio_output.py tests/test_runtime_turn.py tests/test_main_audio.py`: `23 passed`.
  - `./scripts/test_soak_reliability.sh 2`: accepted; `cycles_completed=2/2`, `phase_count=8`, `failed_count=0`, artifact `.artifacts/quality/soak-profile-fast-repeat2.json`.
  - `make check`: `810 passed`.
  - `make security-gate`: `810 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
