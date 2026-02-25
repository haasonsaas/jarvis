# Jarvis Engineering TODO (Fresh Cycle)

Last updated: 2026-02-25

This is a newly reset backlog for the next hardening wave.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Reliability and Error Taxonomy

### 1.1 Boolean env parsing safety (`P0`)
- [x] Treat invalid boolean environment values as "unset" (default behavior), not `False`.
- Why:
  - Invalid env booleans should not silently disable major features.
- Acceptance criteria:
  - `_env_bool` returns `None` for invalid strings.
  - `*_enabled` fields keep default semantics when env is invalid.
- Test plan:
  - Add config tests for invalid bool env values and fallback behavior.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

### 1.2 Startup warnings for invalid booleans (`P1`)
- [x] Include invalid boolean env diagnostics in startup warnings.
- Why:
  - Operators need explicit visibility when env values were ignored.
- Acceptance criteria:
  - `startup_warnings` includes invalid boolean notices.
- Test plan:
  - Assert warnings include invalid boolean keys.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

### 1.3 Service error code normalization guard (`P1`)
- [x] Add validated service error recording helper that normalizes unknown codes.
- Why:
  - Error detail taxonomy should remain machine-readable and bounded.
- Acceptance criteria:
  - Helper maps unknown codes to `unknown_error`.
  - Home Assistant and summary endpoints use validated error recording.
- Test plan:
  - Existing fault-injection tests keep passing with normalized codes.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 2) Observability and Telemetry

### 2.1 Error counter taxonomy coverage (`P1`)
- [x] Ensure telemetry error counters classify `network_client_error` and `http_error`.
- Why:
  - Degraded-state metrics should reflect network/service classes accurately.
- Acceptance criteria:
  - `_refresh_tool_error_counters` increments service-error counts for new taxonomy values.
- Test plan:
  - Add lifecycle unit test with synthetic summary payloads.
- Files:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`

---

## 3) Developer Workflow

### 3.1 Soak command entry points (`P2`)
- [x] Add soak-focused workflow commands in Makefile/scripts/docs.
- Why:
  - Stability checks should be one command for repeatability.
- Acceptance criteria:
  - `make test-soak` target exists.
  - `scripts/test_soak.sh` exists.
  - README documents soak command.
- Test plan:
  - Verify target resolves and command is documented.
- Files:
  - `Makefile`
  - `scripts/test_soak.sh`
  - `README.md`

---

## 4) Execution result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
