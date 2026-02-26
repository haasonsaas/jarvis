# Jarvis Engineering TODO (Next Reliability and Scale Wave)

Last updated: 2026-02-26

This backlog is intentionally broader and longer so we can iterate through multiple passes without running out of high-value engineering work. Focus areas: safety, observability, CI confidence, and maintainability.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Home Assistant Safety and Correctness

### 1.1 Domain/action validation tightening (`P0`)
- [ ] Restrict unknown Home Assistant domains to readonly state checks by default (explicit allowlist for mutating actions).
- [ ] Add tests proving unsupported domain/action pairs are denied before transport.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.2 Sensitive-domain policy expansion (`P0`)
- [ ] Evaluate and add additional sensitive domains (e.g. `vacuum`, `scene`, `script`) where execute confirmation should be stricter.
- [ ] Add tests for sensitive confirmation enforcement.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.3 Entity/domain normalization (`P1`)
- [ ] Normalize whitespace/case in `domain` and `entity_id` handling for deterministic comparisons.
- [ ] Add tests for mixed-case and trailing-space inputs.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.4 Smart-home result semantics (`P1`)
- [ ] Return more structured outcome categories (`noop`, `executed`, `preflight_failed`) in tool text for downstream reasoning consistency.
- [ ] Add tests covering each category branch.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 2) External Integration Hardening

### 2.1 Todoist timeout/backoff posture (`P1`)
- [ ] Add bounded retry (idempotent-safe) for transient Todoist list failures (`timeout`, `network_client_error`).
- [ ] Keep add-task mutation non-retried by default unless explicit idempotency token is introduced.
- [ ] Add tests proving retry policy boundaries.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 2.2 Pushover payload validation (`P1`)
- [ ] Validate `priority` type/range earlier and return `invalid_data` on malformed inputs.
- [ ] Add tests for malformed/overflow priority values.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 2.3 Permission profile diagnostics (`P1`)
- [ ] Extend `system_status` with per-integration “mutation enabled” booleans for quick operator checks.
- [ ] Add tests for profile combinations (`readonly`, `off`, `control`, `allow`).
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 3) Audit and Privacy

### 3.1 Smart-home payload redaction coverage (`P0`)
- [ ] Expand sensitive-key detection list with common HA service fields (e.g. `alarm_code`, `passcode`, `webhook_id`).
- [ ] Add regression tests for newly redacted aliases.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 3.2 Audit event consistency (`P1`)
- [ ] Ensure every external-facing tool has explicit audit records on denied/config/error/success branches.
- [ ] Add a cross-tool test table verifying audit coverage.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 3.3 Audit size management validation (`P2`)
- [ ] Add tests for multi-rotation behavior and backup retention boundaries.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 4) Taxonomy and Telemetry

### 4.1 Taxonomy docs and contracts (`P1`)
- [ ] Document taxonomy definitions and intended usage in a short developer reference doc.
- [ ] Add tests ensuring docs/examples stay aligned with constants.
- Files:
  - `docs/operations/error-taxonomy.md`
  - `src/jarvis/tool_errors.py`
  - `tests/test_main_lifecycle.py`

### 4.2 Unknown detail accounting (`P1`)
- [ ] Track and surface unexpected summary details in telemetry snapshot for debugging taxonomy misses.
- [ ] Add tests proving unknown details are counted/surfaced.
- Files:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`

### 4.3 Metrics snapshot stability (`P2`)
- [ ] Add tests for telemetry averaging under zero/NaN edge cases to avoid runtime regressions.
- Files:
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`

---

## 5) CI and Workflow Quality

### 5.1 CI lane decomposition (`P1`)
- [x] Split CI into separate jobs (`lint`, `tests`, `faults`) for clearer failure locality.
- [x] Keep shared dependency setup efficient.
- Files:
  - `.github/workflows/ci.yml`

### 5.2 Workflow shell hardening (`P2`)
- [ ] Standardize `set -euo pipefail` in bash run blocks where appropriate.
- [ ] Add checks for script executable bits in CI.
- Files:
  - `.github/workflows/ci.yml`
  - `.github/workflows/workflow-sanity.yml`

### 5.3 Optional coverage artifact (`P2`)
- [ ] Add optional coverage XML generation/upload on CI (non-blocking initially).
- Files:
  - `.github/workflows/ci.yml`

---

## 6) Test Suite Maintainability

### 6.1 Shared HTTP mock helpers (`P1`)
- [x] Introduce reusable mock helpers for `aiohttp.ClientSession` patterns to reduce test duplication.
- [x] Refactor service tests to use helper utilities.
- Files:
  - `tests/test_tools.py`
  - `tests/conftest.py`

### 6.2 Parametrize repetitive service cases (`P2`)
- [ ] Parametrize common failure-mode tests (timeout/cancelled/network) across integrations.
- Files:
  - `tests/test_tools.py`

### 6.3 Fault test taxonomy coverage map (`P2`)
- [ ] Add test that ensures every critical taxonomy code is represented in the fault subset selection.
- Files:
  - `tests/test_tools.py`
  - `scripts/test_faults.sh`
  - `Makefile`

---

## 7) Documentation and Runbooks

### 7.1 Home Assistant runbook updates (`P1`)
- [x] Document current redaction behavior and examples in home-control runbook.
- [x] Document cooldown semantics (`dry_run` vs execute).
- Files:
  - `docs/operations/home-control-policy.md`

### 7.2 Integration runbook (`P1`)
- [x] Create runbook for Todoist/Pushover operational setup, profile modes, and troubleshooting.
- Files:
  - `docs/operations/integration-policy.md`
  - `README.md`

### 7.3 README architecture sync (`P2`)
- [ ] Reconcile architecture diagram text with current tool list (Todoist, Pushover, memory/planning).
- Files:
  - `README.md`

---

## 8) Immediate Execution Queue

### 8.1 Start now (`P0`)
- [x] Begin with **6.1 Shared HTTP mock helpers** to reduce service-test maintenance overhead.

### 8.2 Next after 6.1 (`P1`)
- [x] Continue with **5.1 CI lane decomposition**.

### 8.3 Then (`P1`)
- [x] Continue with **7.2 Integration runbook**.
