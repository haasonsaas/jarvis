# Jarvis TODO — Wave 36 (Autonomy Triage + Preference Learning + Operator Guidance)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 36
- Completed: 36
- Remaining: 0

---

## A) Baseline and planning

- [x] `W36-A01` Capture baseline line counts (`__main__.py`, `services.py`) and current branch/gates state.
- [x] `W36-A02` Define scope for proactive triage, preference-learning, operator guidance, and soak enhancements.
- [x] `W36-A03` Ensure every scope item maps to concrete tests before implementation.

## B) Proactive autonomy triage improvements

- [x] `W36-B01` Extend `proactive_assistant` with a new action for triage decisions (`nudge_decision`).
- [x] `W36-B02` Implement severity normalization and deterministic urgency ranking for candidate nudges.
- [x] `W36-B03` Implement policy-aware routing for `interrupt | defer | adaptive` modes.
- [x] `W36-B04` Respect quiet-window behavior in triage routing while allowing high urgency escalation.
- [x] `W36-B05` Add structured triage payload output (interrupt/notify/defer buckets + summary counts).
- [x] `W36-B06` Record proactive triage metrics in runtime proactive state counters.
- [x] `W36-B07` Persist/restore new proactive triage metrics in expansion state runtime helpers.
- [x] `W36-B08` Expose triage metrics in expansion/system status snapshots and contract fields.
- [x] `W36-B09` Update service schema contract for new proactive action arguments.

## C) Preference-learning loop improvements

- [x] `W36-C01` Add a runtime preference parser module for explicit user style directives.
- [x] `W36-C02` Detect user directives for verbosity, tone, pace, and confirmations.
- [x] `W36-C03` Integrate preference detection into conversation loop without altering non-preference turns.
- [x] `W36-C04` Apply detected preferences to active voice profile for the current active user.
- [x] `W36-C05` Persist learned preference summaries to memory when memory is available.
- [x] `W36-C06` Track preference-learning telemetry counters for visibility.
- [x] `W36-C07` Surface recent learned preference state through runtime/operator status payloads.

## D) Operator and status guidance improvements

- [x] `W36-D01` Add operator recommendation synthesis to `runtime_operator_status`.
- [x] `W36-D02` Add health/risk severity rollup for operator recommendations.
- [x] `W36-D03` Include pending-checkpoint/preview signals in recommendations when present.
- [x] `W36-D04` Reduce duplicated status assembly logic in governance domain helpers.
- [x] `W36-D05` Extend voice-attention status with richer acoustic context defaults/fields.
- [x] `W36-D06` Extend system status contract required-field lists for new status structures.

## E) Soak/readiness hardening

- [x] `W36-E01` Extend soak runner with a more live-like profile phase composition.
- [x] `W36-E02` Add artifact assertions/metadata for soak profile phase outcomes.
- [x] `W36-E03` Keep fast/full profile compatibility while adding new profile coverage.

## F) Test coverage expansion

- [x] `W36-F01` Add proactive triage tests for adaptive quiet-window behavior.
- [x] `W36-F02` Add proactive triage tests for interrupt/defer policy behavior.
- [x] `W36-F03` Add expansion-state persistence tests for proactive triage counters.
- [x] `W36-F04` Add unit tests for runtime preference parser behavior.
- [x] `W36-F05` Add lifecycle/runtime tests for learned preference application side effects.
- [x] `W36-F06` Add operator status tests for recommendation/risk payload fields.
- [x] `W36-F07` Update system status tests for new voice/acoustic fields and contract requirements.

## G) Documentation and eval alignment

- [x] `W36-G01` Update docs to describe proactive triage decision action and semantics.
- [x] `W36-G02` Update docs to describe preference-learning behavior and safety boundaries.
- [x] `W36-G03` Extend eval dataset with new contract cases for triage/preferences/operator guidance.

## H) Quality gates and release loop

- [x] `W36-H01` Run targeted pytest for new/changed runtime and services behavior.
- [x] `W36-H02` Run `make check`.
- [x] `W36-H03` Run `make security-gate`.
- [x] `W36-H04` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W36-H05` Update TODO completion summary and snapshot with final metrics.
- [x] `W36-H06` Commit Wave 36 changes with clear message(s) and push to `origin/main`.

---

## Outcome snapshot (completed)

- Core behavior additions:
  - `proactive_assistant(action="nudge_decision")` with policy/quiet-window-aware triage buckets and persisted counters.
  - Conversation-time preference learning for voice profile (`verbosity`, `confirmations`, `pace`, `tone`).
  - Operator status recommendations with severity rollup and actionable codes.
- Status contract expansion:
  - Voice status now includes `acoustic_scene` and `preference_learning`.
  - Observability intent metrics now include `preference_update_turns` and `preference_update_fields`.
  - Expansion proactive status now includes nudge counters/timestamps.
- Soak/readiness:
  - `scripts/run_soak_profile.py` now supports `--profile live` plus artifact checks metadata.
- New files:
  - `src/jarvis/runtime_preferences.py`
  - `tests/test_runtime_preferences.py`
  - `docs/operations/proactive-preference-loop.md`
- Validation status:
  - `make check`: `589 passed`
  - `make security-gate`: `589 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `155/155`
- Size snapshot:
  - `src/jarvis/__main__.py`: `1,714` lines
  - `src/jarvis/tools/services.py`: `1,559` lines
