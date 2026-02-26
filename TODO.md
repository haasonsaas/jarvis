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

### 3.2 Reject boolean coercion in service numeric parsers (`P1`)
- [x] Prevent `True/False` from being implicitly accepted as numeric values for service tool params.

### 3.3 Reject fractional values for integer service params (`P1`)
- [x] Treat non-integer numeric limits as invalid and use safe defaults.

### 3.4 Reject boolean coercion in robot numeric parsers (`P1`)
- [x] Prevent `True/False` from being implicitly accepted as float intensity/motion inputs.

---

## 4) Store-Level Input Hardening

### 4.1 Strict limit normalization in MemoryStore (`P1`)
- [x] Apply strict integer limit parsing inside `MemoryStore` for direct callers.

### 4.2 Strict limit normalization in ToolSummaryStore (`P2`)
- [x] Apply strict integer limit parsing inside `ToolSummaryStore` for direct callers.
- Why:
  - Summary retrieval should be consistent with other strict limit parsing and avoid bool/fraction coercion.
- Acceptance criteria:
  - `ToolSummaryStore.list` rejects bool/fractional limits and uses defaults.
- Test plan:
  - Add tests for `limit=True` and `limit=1.8` fallback behavior.
- Files:
  - `src/jarvis/tool_summary.py`
  - `tests/test_tool_summary.py`

---

## 5) Brain Reliability

### 5.1 Memory context lookup fault tolerance (`P1`)
- [x] Prevent memory lookup failures from aborting response generation.

---

## 6) Developer Workflow

### 6.1 Fault target taxonomy coverage (`P2`)
- [x] Expand `test-faults` selectors to include current normalized taxonomy values.

### 6.2 CI enforcement for checks (`P1`)
- [x] Add GitHub Actions workflow to run lint + tests on pushes and pull requests.

---

## 7) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
