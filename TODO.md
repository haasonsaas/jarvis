# Jarvis TODO — Wave 28 (Automation Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 4
- Completed: 4
- Remaining: 0

---

## A) Decomposition

- [x] `W28-S01` Extract home/automation planning helpers from `services.py` into `src/jarvis/tools/services_automation_runtime.py` (`_home_plan_from_request`, `_slugify_identifier`, `_json_preview`, `_structured_diff`, `_normalize_automation_config`, `_automation_entry_from_draft`).
- [x] `W28-S02` Extract HA automation apply/delete helpers and planner/autonomy helpers (`_apply_ha_automation_config`, `_delete_ha_automation_config`, `_autonomy_tasks`, `_planner_ready_nodes`) into `services_automation_runtime.py`.
- [x] `W28-S03` Replace extracted functions in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W28-Q01` Re-run targeted automation/planner checks and full `make check`, `make security-gate`, and readiness full suite.

---

## Outcome snapshot (current)

- New automation runtime helper module: `src/jarvis/tools/services_automation_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `1,785` lines (from `1,884` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
