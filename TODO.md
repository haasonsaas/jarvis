# Jarvis TODO — Wave 33 (Voice Profile Runtime Extraction)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 22
- Completed: 20
- Remaining: 2

---

## A) Runtime decomposition (continued)

- [x] `W33-A01` Add `src/jarvis/runtime_voice_profile.py` for control parsing + voice profile helpers.
- [x] `W33-A02` Extract `parse_control_bool` helper from `Jarvis` runtime class.
- [x] `W33-A03` Extract `parse_control_choice` helper from `Jarvis` runtime class.
- [x] `W33-A04` Extract active voice user selection helper.
- [x] `W33-A05` Extract active voice profile resolution helper.
- [x] `W33-A06` Extract voice-profile guidance text helper.
- [x] `W33-A07` Keep `Jarvis` wrappers for compatibility with existing tests/importers.
- [x] `W33-A08` Reduce `src/jarvis/__main__.py` further while preserving behavior.

## B) Boundary and regression tests

- [x] `W33-B01` Add `tests/test_runtime_voice_profile.py`.
- [x] `W33-B02` Add parse bool/choice behavior tests.
- [x] `W33-B03` Add active voice user/profile selection tests.
- [x] `W33-B04` Add voice profile guidance append/no-op tests.
- [x] `W33-B05` Extend import-boundary tests with `jarvis.runtime_voice_profile`.
- [x] `W33-B06` Re-run targeted lifecycle tests covering profile + telemetry + runtime-state flows.

## C) Validation gates

- [x] `W33-C01` Run `make check` after extraction changes.
- [x] `W33-C02` Run `make security-gate` after extraction changes.
- [x] `W33-C03` Run `./scripts/jarvis_readiness.sh fast` after extraction changes.
- [x] `W33-C04` Verify strict eval contract remains `151/151` pass.

## D) Hygiene and reporting

- [x] `W33-D01` Update TODO metrics and outcome snapshot with current line counts and gate outputs.
- [ ] `W33-D02` Commit Wave 33 checkpoint.
- [ ] `W33-D03` Push Wave 33 checkpoint to `origin/main`.

---

## Outcome snapshot (in progress)

- `src/jarvis/__main__.py`: `2,278` -> `2,241` lines this wave (`2,677` -> `2,241` across Waves 32-33).
- Added new runtime modules this cycle:
  - `src/jarvis/runtime_state.py`
  - `src/jarvis/runtime_voice_profile.py`
- Expanded telemetry/runtime helper decomposition in `src/jarvis/runtime_telemetry.py`.
- New test coverage modules:
  - `tests/test_runtime_state.py` (`8` tests)
  - `tests/test_runtime_voice_profile.py` (`5` tests)
- Gate status:
  - `make check`: `569 passed`
  - `make security-gate`: `569 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass, strict eval `151/151`
