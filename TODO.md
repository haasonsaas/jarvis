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
- [>] Service-layer storage/network failures are handled, but long-tail failure classes still need broader simulation coverage.
- [>] Cooldown/action history state growth now bounded, but still lacks stress/load characterization.
- [>] Memory/planning reliability needs transactional and lock-contention scenario testing beyond unit happy-paths.
- [>] Runtime observability is stronger, but there is no operator-grade health rollup test for degraded dependency states.
- [>] Large test suite is green, but coverage quality still depends on targeted fault-injection and concurrency cases.

---

## 1) P0 Correctness and Safety

### 1.1 Config validation hardening (`P0`)
- [x] Validate runtime parameter ranges at startup (not just type coercion).
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
- [x] Ensure `_listen_loop` exits quickly on cancellation for local mic mode.
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
- [x] Catch and report non-`aiohttp.ClientError` failures in service calls.
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
- [x] Print a concise capability/status report at startup.
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
- [x] Track counters for turn count, barge-ins, average latencies.
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
- [x] Add optional structured “effect” and “risk” fields to summary records.
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
- [x] Configure SQLite pragmas for reliability/perf baseline.
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
- [x] Make `MemoryStore.close()` idempotent.
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
- [x] Formalize plan status transitions.
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
- [x] Avoid repeated `np.concatenate` for pending buffers.
- Why:
  - Continuous allocation pressure in long-running sessions.
- Acceptance criteria:
  - Replace with deque/chunk ring strategy.
- Test plan:
  - Existing behavior tests pass; add micro-benchmark script if useful.
- Files likely affected:
  - `src/jarvis/__main__.py`

### 4.2 TTS gain controller guardrails (`P2`)
- [x] Validate gain smoothing against pathological chunks.
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
- [x] Add explicit decay behavior when trackers lose target.
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
- [x] Expose current attention source for debugging.
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
- [x] Enforce parity between MCP schema and runtime validation.
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
- [x] Introduce bounded audit log retention or rotation.
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
- [x] Support runtime style modes (terse/composed/friendly).
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
- [x] Startup diagnostics banner and health snapshot.
- [x] Config range validation completeness.
- [x] Service non-client exception envelope.
- [x] Memory DB pragmas and idempotent close.

---

## 9) Current execution wave (this cycle)

### Wave A (now)
- [x] Rewrite TODO into detailed engineering execution plan.
- [x] Implement config boundary validation and tests.
- [x] Add startup diagnostics summary output and tests.
- [x] Harden services network exception envelope.
- [x] Add memory DB pragmas + idempotent close + tests.

### Wave B (next)
- [x] Audio listen-loop cancellation improvements.
- [x] Telemetry counters and periodic status logs.
- [x] Audit retention policy.

### Wave C (current hardening streak)
- [x] Tool-summary and service-status resilience to malformed/non-JSON payloads.
- [x] Memory/planning service handlers wrapped with controlled storage exception envelopes.
- [x] Expand storage failure-path regression tests across memory/planning tools.
- [x] Sanitize non-finite summary timing values at record and read stages.
- [x] Bound action cooldown history growth with retention + cap pruning.
- [x] Add SQLite `busy_timeout` baseline for lock contention tolerance.
- [x] Make `ToolSummaryStore` add/list operations thread-safe.

---

## 11) Deep Backlog (active)

This section is the long-horizon execution plan for continued reliability and maintainability work. Items below are intentionally detailed and should be worked top-down unless blocked.

### 11.1 P0 Service Fault Injection Matrix
- [ ] Build matrix tests for Home Assistant failure classes.
- Why:
  - Current tests cover many errors but not full combinations of timeout/cancel/decode/malformed body scenarios.
- Acceptance criteria:
  - Deterministic tests for:
    - request timeout
    - cancelled request context
    - invalid JSON payload
    - slow response body read failures
  - All return controlled user-facing responses and summary entries.
- Test plan:
  - Patch `aiohttp.ClientSession` with scenario-specific fakes.
- Files likely affected:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 11.2 P0 Memory Transaction Safety
- [ ] Add targeted transaction tests for partial failures in task-plan writes.
- Why:
  - Multi-step operations should never leave half-written plan state.
- Acceptance criteria:
  - Simulated DB failures during `add_task_plan` and step updates do not create inconsistent visible state.
- Test plan:
  - Fault injection around cursor execute calls.
- Files likely affected:
  - `src/jarvis/memory.py`
  - `tests/test_memory.py`

### 11.3 P1 Runtime Health Rollup
- [x] Add compact health-grade score/report for `system_status`.
- Why:
  - Operators need at-a-glance triage signal, not only raw fields.
- Acceptance criteria:
  - Output includes `health_level` (`ok`, `degraded`, `error`) plus reasons array.
- Test plan:
  - Unit tests for each degraded/error trigger combination.
- Files likely affected:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 11.4 P1 Audio Loop Soak Harness
- [ ] Add repeatable synthetic soak test for listen/tts barge-in interplay.
- Why:
  - Concurrency regressions often appear only over many iterations.
- Acceptance criteria:
  - Test utility can run N synthetic turns with barge-ins and report queue/task consistency invariants.
- Test plan:
  - New stress-style test module with deterministic fake audio streams.
- Files likely affected:
  - `tests/test_main_audio.py`
  - `tests/test_integration.py`

### 11.5 P1 Structured Error Codes
- [ ] Standardize service-tool error reasons with machine-readable code fields.
- Why:
  - Downstream consumers and future UI layers need stable error categories.
- Acceptance criteria:
  - Response text remains user-friendly while internal summary/detail includes normalized code set.
- Test plan:
  - Parameterized tests asserting code taxonomy for representative failure paths.
- Files likely affected:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 11.6 P2 Observability Consistency
- [ ] Ensure telemetry snapshots include all critical state dimensions under degradation.
- Why:
  - Current telemetry omits some failure counters and fallback-path markers.
- Acceptance criteria:
  - Snapshot includes counts for storage errors, service errors, and fallback responses.
- Test plan:
  - Unit tests for counter increments and snapshot rendering.
- Files likely affected:
  - `src/jarvis/__main__.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_main_lifecycle.py`

### 11.7 P2 Config and Environment Diagnostics
- [ ] Add explicit startup warnings for ignored/invalid optional env values.
- Why:
  - Silent fallback-to-default can hide bad deployments.
- Acceptance criteria:
  - Startup logs enumerate normalized/fallback fields with concise reason strings.
- Test plan:
  - Config + startup diagnostics tests for invalid optional env values.
- Files likely affected:
  - `src/jarvis/config.py`
  - `src/jarvis/__main__.py`
  - `tests/test_config.py`

### 11.8 P2 Tool-Schema Drift Prevention
- [x] Add CI-oriented consistency helper for schema/runtime maps.
- Why:
  - Prevent accidental additions that bypass parity checks.
- Acceptance criteria:
  - One helper verifies schema map keys and runtime validation map keys are identical.
- Test plan:
  - Fail-fast test if key sets diverge.
- Files likely affected:
  - `src/jarvis/tools/robot.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 11.9 P3 Maintenance and Developer Experience
- [ ] Add `make`/script entry points for lint + tests + focused suites.
- Why:
  - Repeated hardening cycles need stable one-command workflows.
- Acceptance criteria:
  - Documented commands for:
    - full checks
    - fast checks
    - fault-injection tests
- Test plan:
  - Verify scripts run in clean checkout.
- Files likely affected:
  - `README.md`
  - `pyproject.toml`
  - `scripts/` (new)

### 11.10 P3 Risk Review Cadence
- [ ] Add periodic backlog review checklist embedded in TODO.
- Why:
  - Long-running hardening work needs explicit revisit rhythm.
- Acceptance criteria:
  - Checklist includes stale-test detection, flaky-test audit, and unresolved-risk re-prioritization.
- Test plan:
  - N/A (process artifact)
- Files likely affected:
  - `TODO.md`

---

## 10) Definition of Done for this roadmap
- [x] No known P0 bugs open.
- [x] `pytest -q` remains green with added hardening tests.
- [x] Startup prints deterministic capability summary.
- [x] Operator can request status and see core health indicators.
- [x] Memory and tooling layers are resilient to malformed inputs and I/O errors.
