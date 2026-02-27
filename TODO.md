# Jarvis TODO — Wave 37 (Multimodal Grounding + Proactive Context + Endurance Soak)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 33
- Completed: 33
- Remaining: 0

---

## A) Planning and baseline

- [x] `W37-A01` Capture baseline metrics (line counts, test totals, readiness totals).
- [x] `W37-A02` Define Wave 37 scope around multimodal grounding, proactive context, and endurance soak.
- [x] `W37-A03` Map each scope item to concrete tests and contract coverage.

## B) Multimodal grounding quality

- [x] `W37-B01` Add `src/jarvis/runtime_multimodal.py` for reusable grounding scoring helpers.
- [x] `W37-B02` Implement modality signal extraction (face/hand/DOA/STT) with deterministic normalization.
- [x] `W37-B03` Implement aggregate multimodal confidence scoring and confidence-band classification.
- [x] `W37-B04` Add explicit reason-code generation for degraded grounding conditions.
- [x] `W37-B05` Integrate multimodal grounding snapshot into runtime voice status publishing.
- [x] `W37-B06` Persist multimodal snapshot in runtime voice state for system-status visibility.
- [x] `W37-B07` Add per-turn multimodal telemetry counters in conversation runtime.
- [x] `W37-B08` Include multimodal grounding metadata in conversation trace payloads.

## C) Proactive decision quality improvements

- [x] `W37-C01` Extend `proactive_assistant(action="nudge_decision")` with contextual routing inputs.
- [x] `W37-C02` Add context-aware downgrade logic for interrupts (`user_busy`, `conversation_active`, low-presence confidence).
- [x] `W37-C03` Preserve high-urgency escalation semantics while context-aware downgrades are active.
- [x] `W37-C04` Surface context-routing reasons in triage output for operator transparency.
- [x] `W37-C05` Update service schema for new proactive context arguments.

## D) Observability and status contract

- [x] `W37-D01` Extend telemetry snapshot with `multimodal_metrics` aggregate fields.
- [x] `W37-D02` Extend observability status defaults/normalization to include `multimodal_metrics`.
- [x] `W37-D03` Extend system status contract required fields for multimodal observability/voice payloads.
- [x] `W37-D04` Add operator recommendation rule for persistently low multimodal grounding confidence.

## E) Endurance soak improvements

- [x] `W37-E01` Add repeat-cycle support to soak runner (`scripts/run_soak_profile.py`).
- [x] `W37-E02` Add cycle-level metadata and artifact checks for repeated soak execution.
- [x] `W37-E03` Preserve backwards compatibility for existing fast/full/live soak usage.

## F) Test coverage

- [x] `W37-F01` Add unit tests for runtime multimodal scoring/banding/reasons.
- [x] `W37-F02` Add lifecycle tests verifying voice status includes multimodal grounding fields.
- [x] `W37-F03` Add proactive context-routing tests for nudge-decision downgrade behavior.
- [x] `W37-F04` Add operator status tests for multimodal-driven recommendation path.
- [x] `W37-F05` Add contract/status tests for new multimodal required fields.
- [x] `W37-F06` Extend release-tooling tests for soak repeat-cycle artifact metadata.
- [x] `W37-F07` Extend import-boundary tests for new runtime module.

## G) Docs and eval alignment

- [x] `W37-G01` Update operations docs for multimodal grounding and context-aware proactive routing.
- [x] `W37-G02` Extend eval dataset contract cases for multimodal status/observability fields.

## H) Quality and release loop

- [x] `W37-H01` Run targeted pytest for new/changed runtime/services/release modules.
- [x] `W37-H02` Run `make check`.
- [x] `W37-H03` Run `make security-gate`.
- [x] `W37-H04` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W37-H05` Update TODO completion summary and outcome snapshot with final metrics.
- [x] `W37-H06` Commit and push Wave 37 to `origin/main`.

---

## Outcome snapshot (completed)

- Core behavior additions:
  - New runtime multimodal grounding helper in `src/jarvis/runtime_multimodal.py` with confidence scoring, modality signals, and reason codes.
  - Voice/runtime status now includes `multimodal_grounding` payload.
  - Conversation runtime now records per-turn multimodal telemetry and trace metadata.
- Proactive quality:
  - `proactive_assistant(action="nudge_decision")` now supports `context` (`user_busy`, `conversation_active`, `presence_confidence`) and context-aware interrupt downgrade logic.
- Observability/contract:
  - Observability includes `multimodal_metrics`.
  - System status contract includes multimodal required fields for voice and observability.
  - Operator recommendations now include low-multimodal-confidence advisory.
- Endurance soak:
  - `scripts/run_soak_profile.py` now supports `--repeat N` with cycle metadata and expanded artifact checks.
- New tests added:
  - `tests/test_runtime_multimodal.py`
- Validation status:
  - `make check`: `594 passed`
  - `make security-gate`: `594 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `157/157`
- Size snapshot:
  - `src/jarvis/__main__.py`: `1,770` lines
  - `src/jarvis/tools/services.py`: `1,559` lines
  - `src/jarvis/tools/services_domains/trust.py`: `1,159` lines
