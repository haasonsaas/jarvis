# Jarvis Engineering TODO (Integration Hardening Wave)

Last updated: 2026-02-26

This wave implements deeper Home Assistant integration safety, policy gating, preflight validation, idempotency, and operational consistency.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Home Assistant Integration Safety

### 1.1 Permission profile for HA mutation (`P0`)
- [x] Add `HOME_PERMISSION_PROFILE` (`readonly`/`control`) and enforce at tool permission layer.

### 1.2 Sensitive action confirmation gate (`P0`)
- [x] Require `confirm=true` when executing sensitive domains with `dry_run=false`.

### 1.3 Entity domain preflight validation (`P1`)
- [x] Validate `entity_id` domain matches `domain` and reject unsupported action/domain combinations.

### 1.4 Idempotency short-circuit for `turn_on`/`turn_off` (`P1`)
- [x] Preflight state read and no-op when target state already satisfied.

### 1.5 Lightweight HA state cache (`P2`)
- [x] Add short TTL cache for HA state reads used by preflight and `smart_home_state`.

---

## 2) Config and Observability

### 2.1 Config model for HA permission profile (`P1`)
- [x] Normalize/validate `HOME_PERMISSION_PROFILE` in config.
- [x] Emit startup warning on invalid profile values.

### 2.2 Secret/config diagnostics (`P1`)
- [x] Warn when Home Assistant config is partially present (only URL or only token).

### 2.3 System status visibility (`P2`)
- [x] Include active `home_permission_profile` in `system_status.tool_policy` payload.

### 2.4 Environment/docs updates (`P2`)
- [x] Document new HA profile and confirm flow.

---

## 3) Store and Parser Hardening

### 3.1 Strict numeric parsing and coercion defenses (`P1`)
- [x] Service numeric parsers reject bool/fractional limits.
- [x] Robot float parser rejects bool coercion.
- [x] MemoryStore and ToolSummaryStore enforce strict limit parsing for direct callers.

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

### 5.3 Nightly soak workflow (`P2`)
- [x] Add scheduled soak workflow to continuously run stability subset.

---

## 6) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
