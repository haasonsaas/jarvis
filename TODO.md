# Jarvis Engineering TODO (Reliability and Operations Wave)

Last updated: 2026-02-26

This wave focuses on gaps found during deeper review: audit parity for newly-added integrations, stricter upstream API validation, and CI workflow hardening inspired by patterns in `openclaw/openclaw`.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) External Integration Reliability

### 1.1 Todoist response strictness (`P0`)
- [x] Treat 2xx + invalid/non-object JSON as failure instead of silent success.
- [x] Keep normalized taxonomy (`invalid_json`, `http_error`, `auth`, etc.) for summary consistency.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.2 Pushover response strictness (`P0`)
- [x] Parse response body on 200 and require `status == 1` for success.
- [x] Surface API-provided `errors` text on rejection.
- [x] Treat HTTP 400/401 as auth/config error branch.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.3 Integration audit parity (`P0`)
- [x] Add audit records for Todoist and Pushover tools, matching smart-home audit expectations.
- [x] Record safe metadata only (length/preview/IDs/status), no credential fields.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 2) System Observability

### 2.1 Status payload diagnostics (`P1`)
- [x] Include `todoist_configured` and `pushover_configured` booleans in `system_status`.
- [x] Keep profile diagnostics (`home`, `todoist`, `notification`) in policy payload.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 3) CI and Workflow Hygiene

### 3.1 Workflow sanity guardrails (`P1`)
- [x] Add dedicated `workflow-sanity.yml`.
- [x] Enforce no tab characters in workflow YAML files.
- [x] Run `actionlint` with checksum-verified installation.
- Files:
  - `.github/workflows/workflow-sanity.yml`

### 3.2 Documentation of workflow gates (`P2`)
- [x] Document workflow sanity checks in README developer checks section.
- Files:
  - `README.md`

---

## 4) Verification Gates

### 4.1 Local static and tests (`P0`)
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `make test-faults`

---

## 5) Home Assistant Runtime Correctness

### 5.1 Rebind state reset (`P1`)
- [x] Clear action cooldown history in `bind()` so stale in-memory state does not survive profile/config rebinds.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 5.2 State cache invalidation on mutation (`P1`)
- [x] Invalidate cached entity state after successful mutating `smart_home` service call to prevent stale follow-up reads.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 6) CI Throughput and Stability

### 6.1 Workflow concurrency control (`P1`)
- [x] Add `concurrency` groups to CI and workflow-sanity so newer PR pushes cancel older runs.
- [x] Keep nightly soak non-cancelling (`cancel-in-progress: false`) to preserve scheduled signal.
- Files:
  - `.github/workflows/ci.yml`
  - `.github/workflows/workflow-sanity.yml`
  - `.github/workflows/nightly-soak.yml`

### 6.2 Workflow lint toolchain freshness (`P2`)
- [x] Bump `actionlint` installer pin to `1.7.11` in workflow-sanity.
- Files:
  - `.github/workflows/workflow-sanity.yml`

---

## 7) Smart Home UX Safety

### 7.1 Cooldown semantics (`P1`)
- [x] Apply cooldown only to mutating executions (`dry_run=false`), not simulation calls.
- [x] Ensure dry-run calls do not update cooldown history.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 8) Documentation Accuracy

### 8.1 Runtime path and tool map alignment (`P2`)
- [x] Correct audit log path in README structure to `~/.jarvis/audit.jsonl`.
- [x] Update service tool description line to reflect current integrations.
- Files:
  - `README.md`

---

## 9) Audit Privacy Hardening

### 9.1 External integration audit minimization (`P1`)
- [x] Remove raw text previews from Todoist/Pushover success audit payloads.
- [x] Keep only non-sensitive metadata (`length`, `ids`, `status`, `priority`, `title`).
- [x] Add regression tests to prevent reintroduction of preview fields.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 10) Error Taxonomy Precision

### 10.1 Pushover API rejection classification (`P1`)
- [x] Classify `status=0` API rejections as `api_error` (not generic `http_error`).
- [x] Extend service error-code set and tests to cover this branch.
- [x] Keep lifecycle telemetry error taxonomy in sync with service error-code additions.
- Files:
  - `src/jarvis/__main__.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 11) Conversation Quality Fixes

### 11.1 Low-confidence phrase matching (`P2`)
- [x] Normalize confidence-phrase token set to lowercase to match lowercased sentence checks.
- [x] Add regression test for phrase-only sentence (`"I believe..."`) to prevent case regressions.
- Files:
  - `src/jarvis/__main__.py`
  - `tests/test_turn_taking.py`

---

## 12) Audit Coverage Consistency

### 12.1 State-read audit logging (`P2`)
- [x] Add audit entries for `smart_home_state` success and error branches.
- [x] Add tests asserting audit records exist for both success and missing-entity cases.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 13) Schema Precision

### 13.1 Integer field declarations (`P2`)
- [x] Update tool schemas to use `integer` for integer-only args (priority, limit, plan IDs, step indexes).
- [x] Add regression tests for schema type precision on these fields.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 14) Taxonomy Drift Prevention

### 14.1 Telemetry/service taxonomy single-source (`P1`)
- [x] Derive telemetry service-error set from `SERVICE_ERROR_CODES` instead of duplicating literals.
- [x] Keep storage-error subset separation for split counters.
- Files:
  - `src/jarvis/__main__.py`

---

## 15) API Payload Validation Hardening

### 15.1 Todoist list payload shape checks (`P1`)
- [x] Reject task-list responses containing non-object entries as `invalid_json`.
- [x] Add regression test for mixed valid/invalid entry payloads.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 15.2 Pushover status-type checks (`P1`)
- [x] Reject non-integer `status` values as `invalid_json` instead of bubbling to unexpected errors.
- [x] Add regression test for malformed `status` payload (`\"status\": \"ok\"`).
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 16) Audit Secret Redaction

### 16.1 Smart home audit payload redaction (`P0`)
- [x] Redact sensitive keys in smart-home service data before audit logging (e.g. `code`, `pin`, `token`, `secret`).
- [x] Preserve non-sensitive fields for operational traceability.
- [x] Add regression test covering nested dict/list redaction.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 17) Fault Test Coverage Alignment

### 17.1 Fault selector taxonomy sync (`P1`)
- [x] Include `api_error` in `test-faults` selectors (Makefile and script) so API-level rejects stay in fast fault regressions.
- Files:
  - `Makefile`
  - `scripts/test_faults.sh`

---

## 18) Integration Ops Documentation

### 18.1 Profile semantics clarity (`P2`)
- [x] Document exact Todoist and notification profile values and behavior in README safety section.
- Files:
  - `README.md`

---

## 19) Home Action Idempotency Correctness

### 19.1 `turn_off` no-op criteria (`P1`)
- [x] Only short-circuit `turn_off` as no-op when current state is explicitly `off`.
- [x] Do not no-op for `unknown`/`unavailable`; allow execution attempt.
- [x] Add regression test proving `turn_off` executes when state is `unknown`.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

---

## 20) Taxonomy Module Decoupling

### 20.1 Shared error taxonomy extraction (`P1`)
- [x] Extract shared service error taxonomy into side-effect-free module (`jarvis/tool_errors.py`).
- [x] Rewire telemetry to import taxonomy from shared module instead of MCP services module.
- [x] Keep `services.SERVICE_ERROR_CODES` as compatibility alias for existing call sites/tests.

### 20.2 Shared storage-error subset extraction (`P1`)
- [x] Define storage-error subset in shared taxonomy module and consume it in telemetry.
- [x] Add regression assertion that telemetry storage-error set matches shared module constant.
- Files:
  - `src/jarvis/tool_errors.py`
  - `src/jarvis/tools/services.py`
  - `src/jarvis/__main__.py`
  - `tests/test_main_lifecycle.py`
  - `tests/test_tools.py`
