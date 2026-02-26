# Jarvis Engineering TODO (Deep Hardening Cycle)

Last updated: 2026-02-26

This cycle focuses on config strictness, telemetry taxonomy consistency, fault-test workflow coverage, CI enforcement, and task-plan input validation.

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
- Why:
  - JSON numeric values like `1.9` should not mutate plan `1` by truncation.
- Acceptance criteria:
  - `task_plan_update`, `task_plan_summary`, and `task_plan_next` require integer-like IDs.
- Test plan:
  - Add tests for fractional `plan_id` / `step_index` rejection.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 4) Developer Workflow

### 4.1 Fault target taxonomy coverage (`P2`)
- [x] Expand `test-faults` selectors to include current normalized taxonomy values.

### 4.2 CI enforcement for checks (`P1`)
- [x] Add GitHub Actions workflow to run lint + tests on pushes and pull requests.

---

## 5) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
