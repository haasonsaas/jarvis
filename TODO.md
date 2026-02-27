# Jarvis TODO — Wave 32 (Runtime Decomposition Continued)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 24
- Completed: 22
- Remaining: 2

---

## A) Runtime architecture decomposition

- [x] `W32-A01` Create `src/jarvis/runtime_state.py` for runtime-state lifecycle helpers.
- [x] `W32-A02` Extract runtime state load logic from `Jarvis._load_runtime_state`.
- [x] `W32-A03` Extract runtime state save logic from `Jarvis._save_runtime_state`.
- [x] `W32-A04` Extract runtime invariant snapshot/check helpers.
- [x] `W32-A05` Extract runtime profile snapshot/apply helpers.
- [x] `W32-A06` Extract control preset profile/apply helpers.
- [x] `W32-A07` Preserve backwards-compatible `Jarvis` method wrappers.
- [x] `W32-A08` Reduce `src/jarvis/__main__.py` line count by at least 300 lines.

## B) Telemetry decomposition

- [x] `W32-B01` Extract tool error counter summarization into `runtime_telemetry.py`.
- [x] `W32-B02` Extract telemetry snapshot shaping into `runtime_telemetry.py`.
- [x] `W32-B03` Wire `Jarvis._refresh_tool_error_counters` through extracted helper.
- [x] `W32-B04` Wire `Jarvis._telemetry_snapshot` through extracted helper.

## C) Test coverage and boundaries

- [x] `W32-C01` Add new runtime-state-focused test module `tests/test_runtime_state.py`.
- [x] `W32-C02` Add runtime state round-trip persistence/restore test.
- [x] `W32-C03` Add runtime invariant auto-heal behavior test.
- [x] `W32-C04` Add runtime profile apply/persist behavior test.
- [x] `W32-C05` Add runtime profile snapshot sanitization test.
- [x] `W32-C06` Extend `tests/test_import_boundaries.py` with `jarvis.runtime_state` boundary assertion.
- [x] `W32-C07` Run targeted runtime/telemetry lifecycle tests.

## D) Validation and readiness

- [x] `W32-D01` Run `make check` after decomposition changes.
- [x] `W32-D02` Run `make security-gate` after decomposition changes.
- [x] `W32-D03` Run `./scripts/jarvis_readiness.sh fast` to verify readiness contract.

## E) Hygiene and release loop

- [x] `W32-E01` Update TODO outcome snapshot with post-change metrics.
- [ ] `W32-E02` Commit Wave 32 runtime decomposition checkpoint.
- [ ] `W32-E03` Push Wave 32 checkpoint to `origin/main`.

---

## Outcome snapshot (in progress)

- `src/jarvis/__main__.py`: `2,677` -> `2,278` lines.
- New runtime module: `src/jarvis/runtime_state.py` (`560` lines).
- `runtime_telemetry.py` expanded to include telemetry snapshot + error summarization helpers.
- New tests: `tests/test_runtime_state.py` (`8` passing tests).
- Expanded import-boundary assertions include `jarvis.runtime_state`.
- Validation currently green:
  - `make check` (`563 passed`)
  - `make security-gate` (`563 passed`; fault subset `3 passed`)
  - `./scripts/jarvis_readiness.sh fast` (release acceptance fast + strict eval `151/151`)
