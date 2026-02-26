# Jarvis Engineering TODO (Deep Hardening Cycle)

Last updated: 2026-02-26

This cycle focuses on silent-misconfiguration prevention and telemetry taxonomy consistency.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Configuration Robustness

### 1.1 Finite float env parsing (`P0`)
- [x] Treat non-finite float strings (`nan`, `inf`, `-inf`) as invalid env values.
- Why:
  - Non-finite values can bypass range checks and silently degrade runtime behavior.
- Acceptance criteria:
  - `_env_float` falls back to default when parsed value is not finite.
  - Config initialization does not propagate `nan`/`inf` from env.
- Test plan:
  - Add config tests for `DOA_TIMEOUT=nan` and `DOA_CHANGE_THRESHOLD=inf` fallback semantics.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

### 1.2 Finite float startup diagnostics (`P1`)
- [x] Mark non-finite float env values as invalid in startup warnings.
- Why:
  - Operators should be told when numeric env input was ignored.
- Acceptance criteria:
  - `startup_warnings` contains entries for non-finite configured floats.
- Test plan:
  - Extend startup warning assertions with `nan`/`inf` float inputs.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

---

## 2) Telemetry Taxonomy Consistency

### 2.1 Storage taxonomy completeness (`P1`)
- [x] Count `missing_store` failures under storage-error telemetry.
- Why:
  - Missing backing store is a storage-class failure and should be measured with other storage errors.
- Acceptance criteria:
  - `_refresh_tool_error_counters` increments `storage_errors` for `missing_store`.
- Test plan:
  - Add lifecycle test with mixed `missing_store` and `storage_error` payloads.
- Files:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`

### 2.2 Service taxonomy guardrail (`P1`)
- [x] Centralize telemetry service-error code set to avoid drift within `__main__.py`.
- Why:
  - Inlined literals are easy to desynchronize from service module taxonomy evolution.
- Acceptance criteria:
  - Service and storage error detail sets are module constants used by refresh logic.
- Test plan:
  - Existing lifecycle taxonomy tests continue to pass.
- Files:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`

---

## 3) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
