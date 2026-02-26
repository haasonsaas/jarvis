# Jarvis Engineering TODO (Deep Hardening Cycle)

Last updated: 2026-02-26

This cycle focuses on config strictness, telemetry taxonomy consistency, task-plan validation, CI enforcement, brain reliability, and numeric input safety.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Configuration Robustness

### 1.1 Finite float env parsing (`P0`)
- [x] Treat non-finite float strings (`nan`, `inf`, `-inf`) as invalid env values.

### 1.2 Finite float startup diagnostics (`P1`)
- [x] Mark non-finite float env values as invalid in startup warnings.

### 1.3 Required env whitespace strictness (`P1`)
- [x] Reject whitespace-only required env values and return stripped values for required keys.

---

## 2) Telemetry Taxonomy Consistency

### 2.1 Storage taxonomy completeness (`P1`)
- [x] Count `missing_store` failures under storage-error telemetry.

### 2.2 Service taxonomy guardrail (`P1`)
- [x] Centralize telemetry service-error code set to avoid drift within `__main__.py`.

### 2.3 Cross-module taxonomy drift test (`P1`)
- [x] Add regression test ensuring telemetry error sets align with `SERVICE_ERROR_CODES`.

---

## 3) Tool Input Hardening

### 3.1 Exact integer validation for task-plan identifiers (`P1`)
- [x] Reject fractional plan IDs and step indices (no implicit truncation).

### 3.2 Reject boolean coercion in numeric parsers (`P1`)
- [x] Prevent `True/False` from being implicitly accepted as numeric values for service tool params.

### 3.3 Reject fractional values for integer params (`P1`)
- [x] Treat non-integer numeric limits as invalid and use safe defaults.
- Why:
  - Silent truncation (e.g. `2.9 -> 2`) can produce surprising behavior and hidden intent mismatch.
- Acceptance criteria:
  - `_as_int` rejects non-integer floats and non-integer numeric strings.
- Test plan:
  - Add tests for fractional limits in `memory_recent` and `memory_search`.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 4) Brain Reliability

### 4.1 Memory context lookup fault tolerance (`P1`)
- [x] Prevent memory lookup failures from aborting response generation.

---

## 5) Developer Workflow

### 5.1 Fault target taxonomy coverage (`P2`)
- [x] Expand `test-faults` selectors to include current normalized taxonomy values.

### 5.2 CI enforcement for checks (`P1`)
- [x] Add GitHub Actions workflow to run lint + tests on pushes and pull requests.

---

## 6) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
