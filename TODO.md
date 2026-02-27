# Jarvis TODO — Wave 3 (Release Readiness + Runtime Durability)

Last updated: 2026-02-27

This TODO captures the next practical gap-closure pass after the previous roadmap was completed.  
Scope for this wave: make release operations safer, make expansion state durable across restarts, and tighten operator/CI readiness tooling.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 24
- Completed: 24
- Remaining: 0

---

## A) Runtime Persistence Hardening

- [x] `W3-P01` Add dedicated expansion-state persistence path in config (`EXPANSION_STATE_PATH`).
- [x] `W3-P02` Persist roadmap/runtime expansion state (proactive/trust/planner/embodiment/release) to disk.
- [x] `W3-P03` Load persisted expansion state during service bind/restart.
- [x] `W3-P04` Sanitize loaded guest sessions and prune expired sessions on load.
- [x] `W3-P05` Persist expansion state after expansion tool updates.
- [x] `W3-P06` Include richer release-channel state metadata in persisted expansion payload.

## B) Path Configurability and File Placement

- [x] `W3-C01` Add release config path env support (`RELEASE_CHANNEL_CONFIG_PATH`).
- [x] `W3-C02` Add notes capture directory env support (`NOTES_CAPTURE_DIR`).
- [x] `W3-C03` Add quality report output directory env support (`QUALITY_REPORT_DIR`).
- [x] `W3-C04` Wire new paths into services bind lifecycle and defaults.
- [x] `W3-C05` Replace hardcoded notes/quality directories with configured runtime paths.

## C) Release Channel Operations (`integration_hub`)

- [x] `W3-R01` Extend `integration_hub` schema with release channel actions.
- [x] `W3-R02` Implement `release_channel_get` action.
- [x] `W3-R03` Implement `release_channel_set` action with validation + immediate check snapshot.
- [x] `W3-R04` Implement `release_channel_check` action with configurable workspace.
- [x] `W3-R05` Evaluate release-channel checks using configured release-channel JSON.
- [x] `W3-R06` Surface release check details (`last_check_*`, `migration_checks`) in `system_status.expansion.integration_hub`.
- [x] `W3-R07` Update `system_status_contract` required-field map for new integration-hub release keys.

## D) Script and CI Quality Gates

- [x] `W3-S01` Enhance `run_eval_dataset.py` with threshold gates (`--min-pass-rate`, `--max-failed`).
- [x] `W3-S02` Add explicit acceptance failure reasons to eval summary output.
- [x] `W3-S03` Enhance `generate_quality_report.py` with baseline trend comparison support.
- [x] `W3-S04` Add trend section to quality report markdown output.
- [x] `W3-S05` Add combined readiness script (`scripts/jarvis_readiness.sh`).
- [x] `W3-S06` Add `make readiness` target.
- [x] `W3-S07` Add CI workflow to execute readiness gate (`.github/workflows/jarvis-readiness.yml`).

## E) Test and Documentation Coverage

- [x] `W3-T01` Extend config tests for new path/env settings.
- [x] `W3-T02` Add integration tests for `integration_hub` release-channel actions.
- [x] `W3-T03` Add persistence regression test for expansion state across `bind()` reload.
- [x] `W3-T04` Add script-level tests for eval thresholds and quality trend computation.
- [x] `W3-T05` Update release tooling existence checks for new script/workflow/Make target.
- [x] `W3-T06` Update README and `.env.example` for new env vars and readiness commands.

---

## Remaining for this wave

All items above are implemented and validated in this pass.
