# Jarvis Engineering Master TODO

Last updated: 2026-02-25

This is the execution backlog for turning the current Jarvis codebase into a production-grade, continuously running embodied assistant.

## How to read this file
- Status legend:
  - `[ ]` Not started
  - `[-]` In progress
  - `[x]` Implemented in code
  - `[>]` Implemented but needs hardening pass
- Priority labels:
  - `P0` Safety/correctness regressions or crash risks
  - `P1` High-impact product behavior
  - `P2` UX/polish/perf
  - `P3` Nice-to-have or research
- Every task should include:
  - Why it matters
  - Acceptance criteria
  - Test plan
  - Files likely affected

---

## 0) Current State Summary

### Stability Snapshot
- [x] Core unit/integration test suite green.
- [x] Tool input parsing significantly hardened for malformed MCP payloads.
- [x] Lifecycle teardown hardened for partial startup and stop failures.
- [x] STT now honors non-16k sample rates through resampling.
- [x] TTS loop now isolates per-sentence stream failures.

### Known Risk Areas Remaining
- [>] Audio input loop cancellation behavior under blocked stream reads.
- [>] Startup diagnostics visibility (capability/status printout for operator confidence).
- [>] Config boundary validation is minimal in some fields.
- [>] Service network error taxonomy (timeouts, cancellations, unexpected JSON decode errors).
- [>] Memory storage behavior under extreme volumes and long-running sessions.

---

## 1) P0 Correctness and Safety

### 1.1 Config validation hardening (`P0`)
- [ ] Validate runtime parameter ranges at startup (not just type coercion).
- Why:
  - Silent invalid env values can create unstable behavior without obvious failure.
- Acceptance criteria:
  - `Config.__post_init__` rejects invalid values with explicit messages.
  - Ranges enforced for:
    - `vad_threshold` in `[0, 1]`
    - `doa_change_threshold > 0`
    - `doa_timeout > 0`
    - `face_track_fps > 0`
    - `memory_search_limit >= 1`
    - `memory_max_sensitivity` in `[0, 1]`
    - `memory_hybrid_weight` in `[0, 1]`
    - `memory_decay_half_life_days > 0`
    - `memory_mmr_lambda` in `[0, 1]`
    - `backchannel_style` normalized to allowed set with sane fallback
- Test plan:
  - Add unit tests for each invalid range.
  - Add one normalization test for `backchannel_style`.
- Files likely affected:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

### 1.2 Audio input cancellation responsiveness (`P0`)
- [ ] Ensure `_listen_loop` exits quickly on cancellation for local mic mode.
- Why:
  - `sd.InputStream.read()` can block and delay shutdown.
- Acceptance criteria:
  - Cancellation during listen loop exits within bounded time.
  - No hanging tasks on Ctrl+C/SIGTERM.
- Test plan:
  - Add targeted lifecycle test with patched input stream.
- Files likely affected:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`

### 1.3 Service network exception envelope (`P0`)
- [ ] Catch and report non-`aiohttp.ClientError` failures in service calls.
- Why:
  - Unexpected decode errors/timeouts/cancelled contexts should not crash tool handler.
- Acceptance criteria:
  - `smart_home` and `smart_home_state` return controlled error text for all unhandled exceptions.
  - Tool summaries still recorded.
- Test plan:
  - Patch `aiohttp.ClientSession` to throw generic exceptions and assert graceful response.
- Files likely affected:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 2) P1 Product Behavior

### 2.1 Startup diagnostics banner (`P1`)
- [ ] Print a concise capability/status report at startup.
- Why:
  - Operators need immediate confidence in connected subsystems.
- Acceptance criteria:
  - Report includes:
    - Sim vs hardware mode
    - Motion/vision/hands/home enabled flags
    - TTS enabled/disabled reason
    - Memory enabled and storage path
    - Tool policy summary (allow/deny counts)
  - Output appears once after startup success.
- Test plan:
  - Unit test string composition helper.
- Files likely affected:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py` or new startup diagnostics test

### 2.2 Session telemetry snapshot (`P1`)
- [ ] Track counters for turn count, barge-ins, average latencies.
- Why:
  - Needed for production tuning and regression detection.
- Acceptance criteria:
  - Rolling in-memory counters available from a helper method.
  - Optional log snapshot every N turns.
- Test plan:
  - Unit test counter updates from synthetic events.
- Files likely affected:
  - `src/jarvis/__main__.py`
  - `tests/test_integration.py`

### 2.3 Tool summary enrichment (`P1`)
- [ ] Add optional structured “effect” and “risk” fields to summary records.
- Why:
  - Better post-action explainability.
- Acceptance criteria:
  - Backward-compatible schema for existing summary consumers.
- Test plan:
  - Update tool summary tests.
- Files likely affected:
  - `src/jarvis/tool_summary.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 3) P1/P2 Memory and Planning

### 3.1 Memory DB pragmas and reliability (`P1`)
- [ ] Configure SQLite pragmas for reliability/perf baseline.
- Why:
  - Better durability/perf tradeoff for long-running assistant.
- Candidate pragmas:
  - `journal_mode=WAL`
  - `synchronous=NORMAL`
  - `foreign_keys=ON`
- Acceptance criteria:
  - Applied on connection init without breaking tests.
- Test plan:
  - Lightweight test asserting foreign key pragma enabled and no init regression.
- Files likely affected:
  - `src/jarvis/memory.py`
  - `tests/test_memory.py`

### 3.2 Memory close/idempotence (`P1`)
- [ ] Make `MemoryStore.close()` idempotent.
- Why:
  - Defensive cleanup behavior under repeated teardown calls.
- Acceptance criteria:
  - Calling `close()` twice does not raise.
- Test plan:
  - Add dedicated unit test.
- Files likely affected:
  - `src/jarvis/memory.py`
  - `tests/test_memory.py`

### 3.3 Task plan state machine hardening (`P2`)
- [ ] Formalize plan status transitions.
- Why:
  - Prevent inconsistent states as orchestration grows.
- Acceptance criteria:
  - Disallow invalid state transitions.
  - Reopen plan if any step moved from `done` back to active state.
- Test plan:
  - Transition matrix tests.
- Files likely affected:
  - `src/jarvis/memory.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_memory.py`

---

## 4) P2 Audio/Realtime Performance

### 4.1 Reduce allocations in robot-audio listen loop (`P2`)
- [ ] Avoid repeated `np.concatenate` for pending buffers.
- Why:
  - Continuous allocation pressure in long-running sessions.
- Acceptance criteria:
  - Replace with deque/chunk ring strategy.
- Test plan:
  - Existing behavior tests pass; add micro-benchmark script if useful.
- Files likely affected:
  - `src/jarvis/__main__.py`

### 4.2 TTS gain controller guardrails (`P2`)
- [ ] Validate gain smoothing against pathological chunks.
- Why:
  - Prevent clipping/pumping in unusual audio content.
- Acceptance criteria:
  - Gain remains bounded and stable over silence/noise transitions.
- Test plan:
  - Add deterministic tests around `_normalize_tts_chunk`.
- Files likely affected:
  - `src/jarvis/__main__.py`
  - `tests/test_tts.py` or new test file

---

## 5) P2 Perception and Embodiment

### 5.1 Face/hand signal decay and handoff (`P2`)
- [ ] Add explicit decay behavior when trackers lose target.
- Why:
  - Smoother behavioral transitions.
- Acceptance criteria:
  - Face/hand influence fades over configured timeout.
- Test plan:
  - Unit tests for decay to neutral values.
- Files likely affected:
  - `src/jarvis/presence.py`
  - `src/jarvis/vision/face_tracker.py`
  - `src/jarvis/vision/hand_tracker.py`
  - `tests/test_presence.py`

### 5.2 Attention-source observability (`P2`)
- [ ] Expose current attention source for debugging.
- Why:
  - Easier to diagnose turn-taking behavior in real rooms.
- Acceptance criteria:
  - Source label is visible via debug logs and optional status output.
- Test plan:
  - Presence unit tests verify source selection.
- Files likely affected:
  - `src/jarvis/presence.py`
  - `tests/test_presence.py`

---

## 6) P2 Tooling and Policy

### 6.1 Tool payload schema consistency checks (`P2`)
- [ ] Enforce parity between MCP schema and runtime validation.
- Why:
  - Avoid drift where schema claims allowed fields not actually accepted.
- Acceptance criteria:
  - All required fields enforced and defaults explicit in both places.
- Test plan:
  - Add schema/runtime consistency smoke tests.
- Files likely affected:
  - `src/jarvis/tools/robot.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 6.2 Audit retention policy (`P2`)
- [ ] Introduce bounded audit log retention or rotation.
- Why:
  - Prevent unbounded disk growth.
- Acceptance criteria:
  - Configurable max file size or rolling file count.
- Test plan:
  - Unit test rotation trigger.
- Files likely affected:
  - `src/jarvis/tools/services.py`
  - `src/jarvis/config.py`
  - `tests/test_tools.py`

---

## 7) P3 UX and Personality

### 7.1 Operator-friendly status command (`P3`)
- [x] Add a `system_status` tool for quick diagnosis.
- Why:
  - Reduces guesswork during demos and failures.
- Acceptance criteria:
  - Returns key subsystem states and recent errors.
- Test plan:
  - Integration test for non-empty status payload.
- Files likely affected:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 7.2 Persona style toggles (`P3`)
- [ ] Support runtime style modes (terse/composed/friendly).
- Why:
  - Better user preference alignment.
- Acceptance criteria:
  - Config + memory preference feed into prompt style instructions.
- Test plan:
  - Unit tests for prompt composition.
- Files likely affected:
  - `src/jarvis/brain.py`
  - `src/jarvis/config.py`
  - `tests/test_brain.py`

---

## 8) What was completed recently

### Already landed in recent passes
- [x] Robust tool argument parsing in robot and services tool handlers.
- [x] Safer lifecycle shutdown across startup/teardown failures.
- [x] Session ID persistence in Brain from SDK init messages.
- [x] TTS worker resilience to per-sentence stream failures.
- [x] STT sample-rate handling through explicit resampling.
- [x] Tracker constructor validation and stop-state cleanup.
- [x] Memory tag decode hardening and DB edge-case tests.
- [x] Audit serialization hardened for non-JSON payload data.

### Follow-up hardening needed
- [>] Startup diagnostics banner and health snapshot.
- [>] Config range validation completeness.
- [>] Service non-client exception envelope.
- [>] Memory DB pragmas and idempotent close.

---

## 9) Current execution wave (this cycle)

### Wave A (now)
- [-] Rewrite TODO into detailed engineering execution plan.
- [-] Implement config boundary validation and tests.
- [-] Add startup diagnostics summary output and tests.
- [-] Harden services network exception envelope.
- [-] Add memory DB pragmas + idempotent close + tests.

### Wave B (next)
- [x] Audio listen-loop cancellation improvements.
- [x] Telemetry counters and periodic status logs.
- [x] Audit retention policy.

---

## 10) Definition of Done for this roadmap
- [ ] No known P0 bugs open.
- [ ] `pytest -q` remains green with added hardening tests.
- [ ] Startup prints deterministic capability summary.
- [ ] Operator can request status and see core health indicators.
- [ ] Memory and tooling layers are resilient to malformed inputs and I/O errors.
