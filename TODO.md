# Jarvis Engineering TODO (External Integration Wave)

Last updated: 2026-02-26

This wave adds external task and notification integrations with explicit policy gates, config diagnostics, and test coverage.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Home Assistant Safety (Completed)

### 1.1 Permission profile and gating (`P0`)
- [x] `HOME_PERMISSION_PROFILE` (`readonly`/`control`) enforced in tool policy.

### 1.2 Sensitive confirmation flow (`P0`)
- [x] Sensitive execute requires `confirm=true` when `dry_run=false`.

### 1.3 Preflight validation and idempotency (`P1`)
- [x] Domain/entity/action preflight validation.
- [x] Idempotent no-op short-circuit for `turn_on`/`turn_off`.
- [x] Shared HA state helper and short TTL cache.

---

## 2) New External Integrations

### 2.1 Todoist tools (`P0`)
- [x] Add `todoist_add_task` and `todoist_list_tasks` tools.
- [x] Add Todoist schemas and runtime required field parity.
- [x] Add HTTP timeout/auth/network handling with normalized telemetry errors.
- Files:
  - `src/jarvis/tools/services.py`
  - `src/jarvis/brain.py`
  - `tests/test_tools.py`

### 2.2 Notification tool (`P0`)
- [x] Add `pushover_notify` tool.
- [x] Add schema and runtime required field parity.
- [x] Add timeout/auth/network handling with normalized telemetry errors.
- Files:
  - `src/jarvis/tools/services.py`
  - `src/jarvis/brain.py`
  - `tests/test_tools.py`

### 2.3 Integration permission profiles (`P1`)
- [x] Add `TODOIST_PERMISSION_PROFILE` (`readonly`/`control`) and enforce add-task mutation gate.
- [x] Add `NOTIFICATION_PERMISSION_PROFILE` (`off`/`allow`) and enforce notification gate.
- Files:
  - `src/jarvis/config.py`
  - `src/jarvis/tools/services.py`
  - `tests/test_config.py`
  - `tests/test_tools.py`

### 2.4 Config diagnostics for integrations (`P1`)
- [x] Warn on partial Todoist config.
- [x] Warn on partial Pushover config.
- [x] Warn on invalid integration permission profile env values.
- Files:
  - `src/jarvis/config.py`
  - `tests/test_config.py`

---

## 3) Docs and Env Surface

### 3.1 Environment template updates (`P1`)
- [x] Add Todoist and Pushover env keys and policy profile keys.
- Files:
  - `.env.example`

### 3.2 README updates (`P1`)
- [x] Document Todoist/Pushover integrations and policy profile controls.
- Files:
  - `README.md`

---

## 4) Ops and CI

### 4.1 Nightly soak (`P2`)
- [x] Scheduled soak workflow remains in place.

### 4.2 Home control runbook (`P2`)
- [x] Operational policy-layer runbook remains in place.

---

## 5) Execution Result
- [x] Lint clean: `uv run ruff check src tests`
- [x] Test suite green: `uv run pytest -q`
- [x] Fault subset green: `scripts/test_faults.sh`
