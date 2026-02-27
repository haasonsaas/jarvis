# Jarvis TODO — Wave 13 (Turn + Server Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 5
- Completed: 5
- Remaining: 0

---

## A) Decomposition

- [x] `W13-S01` Wire `src/jarvis/runtime_turn.py` helpers into `Jarvis` turn-lifecycle methods while preserving method names/signatures for test compatibility.
- [x] `W13-S02` Extract MCP tool registration/build logic from `src/jarvis/tools/services.py` into `src/jarvis/tools/services_server.py`.
- [x] `W13-S03` Keep backward-compatible exports in `services.py` used by tests/importers (`SERVICE_TOOL_SCHEMAS`, `SERVICE_RUNTIME_REQUIRED_FIELDS`, domain handler re-exports, and `create_services_server`).
- [x] `W13-S04` Resolve linter shadowing in health rollup helper (`memory_status` parameter rename) and update governance call sites.

## B) Quality and verification

- [x] `W13-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after Wave 13 extraction items.

---

## Outcome snapshot (current)

- `src/jarvis/__main__.py` now delegates conversation-turn classification/carryover/trace summary logic to `src/jarvis/runtime_turn.py`.
- `src/jarvis/tools/services.py` no longer contains MCP tool wrapper construction; server/tool registration now lives in `src/jarvis/tools/services_server.py`.
- Size reductions:
  - `src/jarvis/__main__.py`: `3,258` lines (from `3,404` before this wave).
  - `src/jarvis/tools/services.py`: `4,102` lines (from `4,551` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
