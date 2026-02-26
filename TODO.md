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
