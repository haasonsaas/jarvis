# Jarvis Engineering TODO (Deep Hardening Cycle)

Last updated: 2026-02-26

This cycle focuses on config strictness, telemetry taxonomy consistency, task-plan validation, CI enforcement, and brain memory-failure resilience.

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

---

## 4) Brain Reliability

### 4.1 Memory context lookup fault tolerance (`P1`)
- [x] Prevent memory lookup failures from aborting response generation.
- Why:
  - Pre-query memory enrichment is optional and should degrade gracefully when storage is unavailable.
- Acceptance criteria:
  - `Brain.respond` continues to query Claude when `search_v2` raises.
- Test plan:
  - Add brain test with `search_v2` raising runtime error and assert query still executes.
- Files:
  - `src/jarvis/brain.py`
  - `tests/test_brain.py`

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
