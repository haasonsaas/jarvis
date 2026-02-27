# Jarvis TODO — Wave 114/114 No-Hardware Reliability Expansion

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Previous wave archive: `docs/operations/todo-archive-2026-02-27.md`
- Active items: 12
- Completed: 12
- Remaining: 0

---

## Current state
- Major runtime decomposition and reliability waves through 112 are complete.
- Wave 113 (no-hardware expansion) is complete.
- Wave 114 (chaos + operator UX contract hardening) is complete.

## Wave 113 (completed)
- [x] Build a simulation-first acceptance suite for full voice loop edge cases.
- [x] Expand eval dataset to 250+ cases with stronger contract gating (`min_cases`, unique IDs, non-empty `expected_tools`).
- [x] Add CI quality trend gates for soak/fault artifacts using delta thresholds and baseline config.
- [x] Add fault/soak trend baseline config and workflow wiring for nightly/quality report pipelines.
- [x] Prepare a hardware bring-up checklist and enforce it via docs tests.
- [x] Standardize Python script shebangs to `#!/usr/bin/env python` for local environment portability.

## Wave 114 (completed)
- [x] Add deterministic fault-chaos permutation runner with recovery replay/idempotence phase checks.
- [x] Add `test_fault_chaos.sh`, `make test-fault-chaos`, and workflow support for chaos profile execution.
- [x] Add operator-status compatibility snapshot artifact under `docs/evals/`.
- [x] Add operator-status snapshot contract test to ensure stable required payload paths.
- [x] Add operator-status stress recommendation-code contract test for high-risk/degraded scenarios.
- [x] Wire operator-status contract checks into release acceptance core flow.
