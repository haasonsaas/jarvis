# Jarvis TODO — Wave 35 (Run Loop + Listen Loop + Operator Status Extraction)

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

## A) Planning and baseline

- [x] `W35-A01` Capture current baseline metrics for `src/jarvis/__main__.py`, tests, and gates.
- [x] `W35-A02` Identify all dependencies needed to safely extract `run`, `_listen_loop`, and `_operator_status_provider`.
- [x] `W35-A03` Define module boundaries for conversation runtime, audio/listen runtime, and operator status runtime.
- [x] `W35-A04` Keep backwards-compatible wrappers on `Jarvis` methods so existing callers/tests do not break.

## B) Run-loop extraction

- [x] `W35-B01` Create `src/jarvis/runtime_conversation.py`.
- [x] `W35-B02` Extract `Jarvis.run` logic into `runtime_conversation.run(runtime)`.
- [x] `W35-B03` Preserve startup, task scheduling, and shutdown/cancellation semantics in extracted function.
- [x] `W35-B04` Preserve telemetry updates and lifecycle trace recording paths from run loop.
- [x] `W35-B05` Preserve repair/confirmation/follow-up carryover branches from run loop.
- [x] `W35-B06` Preserve memory correction fast-path handling from run loop.

## C) Listen and response extraction

- [x] `W35-C01` Extract `_listen_loop` into `runtime_conversation.listen_loop(...)`.
- [x] `W35-C02` Parameterize listen loop with audio adapters (`sounddevice`, resample, mono conversion).
- [x] `W35-C03` Preserve robot-audio and local-microphone behavior parity.
- [x] `W35-C04` Preserve barge-in and VAD/DOA signal updates in extracted listen flow.
- [x] `W35-C05` Extract `_respond_and_speak` into `runtime_conversation.respond_and_speak(runtime, text)`.
- [x] `W35-C06` Preserve filler-task, first-token/audio latency tracking, and TTS queue behavior.

## D) Operator status extraction

- [x] `W35-D01` Create `src/jarvis/runtime_operator_status.py`.
- [x] `W35-D02` Extract `_operator_status_provider` enrichment logic into runtime helper.
- [x] `W35-D03` Preserve auth-risk classification logic and mode normalization.
- [x] `W35-D04` Preserve episodic timeline and conversation trace status aggregation.
- [x] `W35-D05` Preserve operator control preset/runtime-profile status fields.

## E) Test coverage and boundaries

- [x] `W35-E01` Add `tests/test_runtime_conversation.py` for extracted run/listen/response helpers where practical.
- [x] `W35-E02` Add tests for operator status helper output shaping.
- [x] `W35-E03` Extend `tests/test_import_boundaries.py` for new runtime modules.
- [x] `W35-E04` Re-run targeted lifecycle tests affected by extraction.
- [x] `W35-E05` Ensure existing operator/runtime lifecycle tests remain green.

## F) Quality gates and release loop

- [x] `W35-F01` Run `make check`.
- [x] `W35-F02` Run `make security-gate`.
- [x] `W35-F03` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W35-F04` Verify strict eval dataset acceptance remains `151/151`.
- [x] `W35-F05` Update TODO completion summary and outcome snapshot with final metrics.
- [x] `W35-F06` Commit extraction checkpoint(s) with clear messages.
- [x] `W35-F07` Push all Wave 35 commits to `origin/main`.

---

## Outcome snapshot (completed)

- `src/jarvis/__main__.py`: `2,170` -> `1,604` lines.
- New runtime modules added:
  - `src/jarvis/runtime_conversation.py`
  - `src/jarvis/runtime_operator_status.py`
- New tests added:
  - `tests/test_runtime_conversation.py`
  - `tests/test_runtime_operator_status.py`
- Extended import boundaries:
  - `tests/test_import_boundaries.py` includes `runtime_conversation` and `runtime_operator_status`.
- Validation status:
  - `make check`: `579 passed`
  - `make security-gate`: `579 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass, strict eval `151/151`
