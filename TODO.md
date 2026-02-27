# Jarvis TODO — Wave 31 (Architecture + Reliability + Personality)

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

## A) Architecture decomposition

- [x] `W31-A01` Replace stale Wave 30 TODO and reset with Wave 31 scope tied to current repository shape.
- [x] `W31-A02` Extract telemetry + STT analytics helpers from `src/jarvis/__main__.py` into a dedicated runtime helper module.
- [x] `W31-A03` Keep compatibility wrappers on `Jarvis` class methods used by tests/importers.
- [x] `W31-A04` Reduce `__main__.py` line count by moving pure/helper logic out of the file.
- [x] `W31-A05` Extract planner reminder payload helper logic from `services_domains/planner.py` into `services_domains/planner_runtime.py`.
- [x] `W31-A06` Extract calendar window parsing helper logic from `services_domains/integrations.py` into `services_domains/integrations_runtime.py`.
- [x] `W31-A07` Add import-boundary tests for new domain runtime modules to ensure clean import graph.
- [x] `W31-A08` Add import-boundary tests for new runtime helper module used by `__main__.py`.

## B) Eval coverage expansion

- [x] `W31-E01` Expand `docs/evals/assistant-contract.json` from 91 to at least 150 cases.
- [x] `W31-E02` Add multi-turn continuity/repair/confirmation cases (follow-up carryover, correction flows).
- [x] `W31-E03` Add long-horizon autonomy cases (schedule/checkpoint/cycle/status combinations).
- [x] `W31-E04` Add recovery and dead-letter lifecycle cases (enqueue/list/replay/status transitions).
- [x] `W31-E05` Add area-policy, automation apply/rollback, and preview-token gating edge cases.
- [x] `W31-E06` Add personality/voice-profile contract cases (`persona_style`, `tone`, `pace`, `verbosity`).
- [x] `W31-E07` Keep strict pass-rate gate at 100% for readiness profile.

## C) Soak and robustness

- [x] `W31-R01` Add long-duration simulation soak profile script with explicit phases.
- [x] `W31-R02` Add deterministic outage/recovery phase to soak flow (HA/webhook fault profile runs).
- [x] `W31-R03` Add checkpoint resume verification phase using planner autonomy tooling.
- [x] `W31-R04` Add retry/circuit-breaker verification phase with explicit assertions.
- [x] `W31-R05` Wire new soak profile into `Makefile` targets for repeatable execution.
- [x] `W31-R06` Capture machine-readable soak artifact summary in `.artifacts/quality/`.

## D) Personality A/B + drift checks

- [x] `W31-P01` Add script to run persona/tone A/B batches over eval-style prompts.
- [x] `W31-P02` Implement scoring for brevity drift and confirmation-friction drift.
- [x] `W31-P03` Emit JSON + markdown report artifacts for A/B runs.
- [x] `W31-P04` Document A/B workflow in `docs/operations/personality-research.md`.
- [x] `W31-P05` Add CI-ready command wrapper for personality checks.

## E) Hygiene, docs, and release readiness

- [x] `W31-H01` Update stale line-count references in docs/TODO outcome snapshots.
- [x] `W31-H02` Re-run `make check`.
- [x] `W31-H03` Re-run `make security-gate`.
- [x] `W31-H04` Re-run full readiness suite (`./scripts/jarvis_readiness.sh full`).
- [x] `W31-H05` Commit/push in small checkpoints with messages tied to track IDs.
- [x] `W31-H06` Final sweep for untracked files, stale artifacts, and TODO completion accuracy.

---

## Outcome snapshot (completed)

- `src/jarvis/__main__.py` reduced from `2,919` to `2,677` lines.
- Domain decomposition added:
  - `src/jarvis/tools/services_domains/planner_runtime.py`
  - `src/jarvis/tools/services_domains/integrations_runtime.py`
  - import-boundary coverage in `tests/test_import_boundaries.py`.
- Eval contract expanded from `91` to `151` strict passing cases.
- New phased soak profiles added with machine-readable artifacts:
  - `scripts/run_soak_profile.py`
  - `scripts/test_soak.sh` (fast profile)
  - `scripts/test_soak_extended.sh` (full profile)
- Personality A/B harness and drift checks added:
  - `docs/evals/personality-ab-prompts.json`
  - `scripts/personality_ab_eval.py`
  - `scripts/test_personality.sh`
- Full gates are green:
  - `make check` (`558 passed`)
  - `make security-gate` (`558 passed`; fault subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`151/151` strict eval)
