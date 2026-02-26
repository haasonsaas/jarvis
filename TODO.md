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
- Why:
  - Operations should be able to switch to state-only mode without code changes.
- Acceptance criteria:
  - `smart_home` is denied in `readonly` profile.
  - `smart_home_state` remains available.
- Files:
  - `src/jarvis/config.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_config.py`
  - `tests/test_tools.py`

### 1.2 Sensitive action confirmation gate (`P0`)
- [x] Require `confirm=true` when executing sensitive domains with `dry_run=false`.
- Why:
  - Prevent accidental lock/alarm/cover actuation.
- Acceptance criteria:
  - Mutating sensitive actions return policy error unless explicitly confirmed.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.3 Entity domain preflight validation (`P1`)
- [x] Validate `entity_id` domain matches `domain` and reject unsupported action/domain combinations.
- Why:
  - Catch malformed and semantically invalid requests before network calls.
- Acceptance criteria:
  - `light` + `switch.kitchen` is rejected.
  - Unsupported action for known domain is rejected.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.4 Idempotency short-circuit for `turn_on`/`turn_off` (`P1`)
- [x] Preflight state read and no-op when target state already satisfied.
- Why:
  - Avoid unnecessary HA writes and reduce device churn.
- Acceptance criteria:
  - `turn_on` returns no-op when state already on.
  - `turn_off` returns no-op when state already off.
- Files:
  - `src/jarvis/tools/services.py`
  - `tests/test_tools.py`

### 1.5 Lightweight HA state cache (`P2`)
- [x] Add short TTL cache for HA state reads used by preflight and `smart_home_state`.
- Why:
  - Reduce duplicate state round-trips during rapid command bursts.
- Acceptance criteria:
  - Shared helper backs both preflight and state endpoint.
- Files:
  - `src/jarvis/tools/services.py`

---

## 2) Config and Observability

### 2.1 Config model for HA permission profile (`P1`)
- [x] Normalize/validate `HOME_PERMISSION_PROFILE` in config.
- [x] Emit startup warning on invalid profile values.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

### 2.2 System status visibility (`P2`)
- [x] Include active `home_permission_profile` in `system_status.tool_policy` payload.
- Files:
  - `src/jarvis/tools/services.py`

### 2.3 Environment/docs updates (`P2`)
- [x] Document new HA profile and confirm flow.
- Files:
  - `.env.example`
  - `README.md`

---

## 3) Existing Hardening Carry-Forward

### 3.1 Strict numeric parsing and coercion defenses (`P1`)
- [x] Service numeric parsers reject bool/fractional limits.
- [x] Robot float parser rejects bool coercion.
- [x] MemoryStore and ToolSummaryStore enforce strict limit parsing for direct callers.

### 3.2 Brain resilience (`P1`)
- [x] Memory context lookup failure no longer aborts response flow.

---

## 4) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
