# Jarvis TODO — Wave 34 (Startup + Operator Schema Extraction)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 18
- Completed: 16
- Remaining: 2

---

## A) Runtime decomposition (startup path)

- [x] `W34-A01` Add `src/jarvis/runtime_startup.py` for startup/runtime schema helpers.
- [x] `W34-A02` Extract operator control schema builder from `Jarvis._operator_control_schema`.
- [x] `W34-A03` Extract startup strict blocker validation from `Jarvis._startup_blockers`.
- [x] `W34-A04` Keep `Jarvis` wrappers to preserve compatibility for existing callers/tests.
- [x] `W34-A05` Reduce `src/jarvis/__main__.py` below 2,200 LOC.

## B) Test and boundary coverage

- [x] `W34-B01` Add `tests/test_runtime_startup.py` for extracted startup/schema helpers.
- [x] `W34-B02` Validate schema action + enum coverage in unit tests.
- [x] `W34-B03` Validate startup strict blocker enforcement in unit tests.
- [x] `W34-B04` Extend `tests/test_import_boundaries.py` with `jarvis.runtime_startup`.
- [x] `W34-B05` Re-run targeted lifecycle tests for runtime-state, telemetry, and voice-profile paths.

## C) Validation gates

- [x] `W34-C01` Run `make check` after startup extraction.
- [x] `W34-C02` Run `make security-gate` after startup extraction.
- [x] `W34-C03` Run `./scripts/jarvis_readiness.sh fast` after startup extraction.
- [x] `W34-C04` Confirm strict eval contract still passes (`151/151`).

## D) Hygiene and release loop

- [x] `W34-D01` Refresh TODO metrics/outcome snapshot with current counts and gate outputs.
- [ ] `W34-D02` Commit Wave 34 checkpoint.
- [ ] `W34-D03` Push Wave 34 checkpoint to `origin/main`.

---

## Outcome snapshot (in progress)

- `src/jarvis/__main__.py`: `2,241` -> `2,170` lines this wave (`2,677` -> `2,170` across Waves 32-34).
- New runtime helper modules added across recent waves:
  - `src/jarvis/runtime_state.py`
  - `src/jarvis/runtime_voice_profile.py`
  - `src/jarvis/runtime_startup.py`
- New unit coverage modules added across recent waves:
  - `tests/test_runtime_state.py`
  - `tests/test_runtime_voice_profile.py`
  - `tests/test_runtime_startup.py`
- Current gate status:
  - `make check`: `573 passed`
  - `make security-gate`: `573 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass, strict eval `151/151`
