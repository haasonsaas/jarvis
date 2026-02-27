# Jarvis TODO — Wave 38 (Proactive Dedupe + Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 32
- Completed: 32
- Remaining: 0

---

## A) Wave framing

- [x] `W38-A01` Identify next high-risk behavior area after multimodal rollout.
- [x] `W38-A02` Select proactive nudge routing as next hardening target.
- [x] `W38-A03` Define decomposition goal: extract reusable proactive runtime helpers from trust domain.

## B) Proactive runtime decomposition

- [x] `W38-B01` Add `src/jarvis/tools/services_proactive_runtime.py`.
- [x] `W38-B02` Move deterministic severity normalization into runtime helper.
- [x] `W38-B03` Move nudge scoring function into runtime helper.
- [x] `W38-B04` Move nudge bucket policy function into runtime helper.
- [x] `W38-B05` Add candidate fingerprint helper for dedupe tracking.
- [x] `W38-B06` Add recent-dispatch prune helper with bounded retention.
- [x] `W38-B07` Add recent-dispatch lookup helper.
- [x] `W38-B08` Add recent-dispatch append helper.
- [x] `W38-B09` Add reason histogram helper for triage explainability.

## C) Proactive anti-spam behavior

- [x] `W38-C01` Add `dedupe_window_sec` argument to `proactive_assistant(action="nudge_decision")`.
- [x] `W38-C02` Implement duplicate suppression for interrupt/notify candidates.
- [x] `W38-C03` Emit explicit defer reason `duplicate_recent_dispatch`.
- [x] `W38-C04` Preserve capacity and urgency routing after dedupe pass.
- [x] `W38-C05` Track per-call `dedupe_suppressed_count` in response payload.
- [x] `W38-C06` Add `reason_counts` to nudge decision payload.

## D) Proactive runtime state and status

- [x] `W38-D01` Extend proactive state defaults with dedupe counters/timestamps/cache.
- [x] `W38-D02` Add proactive state reset support for new dedupe fields.
- [x] `W38-D03` Add proactive state load-path normalization for dedupe fields.
- [x] `W38-D04` Extend system expansion snapshot with dedupe metrics.
- [x] `W38-D05` Extend status contract proactive-required fields for dedupe metrics.

## E) Schema, docs, and eval dataset

- [x] `W38-E01` Extend proactive tool schema with `dedupe_window_sec`.
- [x] `W38-E02` Update operations doc for dedupe routing behavior and reason codes.
- [x] `W38-E03` Add eval case for proactive status dedupe metrics.
- [x] `W38-E04` Add eval case for nudge dedupe payload contract.

## F) Tests and boundaries

- [x] `W38-F01` Add unit tests for proactive runtime helper module.
- [x] `W38-F02` Add service-level dedupe behavior test for repeated candidates.
- [x] `W38-F03` Extend status tests for proactive dedupe fields.
- [x] `W38-F04` Extend contract tests for proactive dedupe required fields.
- [x] `W38-F05` Extend schema tests for `dedupe_window_sec` type.
- [x] `W38-F06` Add import-boundary guard for proactive runtime helper module.

## G) Quality loop

- [x] `W38-G01` Run focused lint + targeted pytest for proactive/status changes.
- [x] `W38-G02` Run `make check`.
- [x] `W38-G03` Run `make security-gate`.
- [x] `W38-G04` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W38-G05` Commit and push Wave 38.

---

## Outcome snapshot (completed)

- Runtime decomposition:
  - Added dedicated proactive runtime helpers in `src/jarvis/tools/services_proactive_runtime.py`.
  - `trust.py` now delegates nudge score/bucket/fingerprint/dedupe utility logic to runtime helpers.
- Proactive quality:
  - `nudge_decision` now supports dedupe suppression window (`dedupe_window_sec`, default 600 sec).
  - Duplicate recently-dispatched candidates are downgraded to `defer` with reason `duplicate_recent_dispatch`.
  - Response now includes `dedupe_suppressed_count` and `reason_counts`.
- Status and contract:
  - Proactive expansion status now exposes:
    - `nudge_deduped_total`
    - `last_nudge_dedupe_at`
    - `nudge_recent_dispatch_count`
  - System status contract now requires those proactive fields.
- Persistence:
  - Proactive dedupe counters/history are reset + reloaded correctly through expansion state routines.
- Validation results:
  - Focused pytest/lint: pass
  - `make check`: `600 passed`
  - `make security-gate`: `600 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
