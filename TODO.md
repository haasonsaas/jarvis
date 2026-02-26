# Jarvis Engineering TODO (Deep Hardening Cycle)

Last updated: 2026-02-26

This cycle focuses on config strictness, telemetry taxonomy consistency, fault-test workflow coverage, and CI enforcement.

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
- Why:
  - `ANTHROPIC_API_KEY="   "` should be treated as missing, not accepted.
- Acceptance criteria:
  - `_require_env` raises when the value is blank after trimming.
  - `_require_env` returns trimmed value for valid input.
- Test plan:
  - Add config tests for whitespace-only and padded required env values.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

---

## 2) Telemetry Taxonomy Consistency

### 2.1 Storage taxonomy completeness (`P1`)
- [x] Count `missing_store` failures under storage-error telemetry.

### 2.2 Service taxonomy guardrail (`P1`)
- [x] Centralize telemetry service-error code set to avoid drift within `__main__.py`.

### 2.3 Cross-module taxonomy drift test (`P1`)
- [x] Add regression test ensuring telemetry error sets align with `SERVICE_ERROR_CODES`.

---

## 3) Developer Workflow

### 3.1 Fault target taxonomy coverage (`P2`)
- [x] Expand `test-faults` selectors to include current normalized taxonomy values.

### 3.2 CI enforcement for checks (`P1`)
- [x] Add GitHub Actions workflow to run lint + tests on pushes and pull requests.
- Why:
  - Local checks are useful but unenforced; CI should block regressions automatically.
- Acceptance criteria:
  - Workflow runs on `push` and `pull_request`.
  - Workflow installs dependencies and executes lint + tests.
- Test plan:
  - Validate YAML and keep local check scripts as CI commands.
- Files:
  - `.github/workflows/ci.yml`
  - `README.md`

---

## 4) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
