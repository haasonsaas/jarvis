# Jarvis TODO — Wave 64 (Home Assistant Tool Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 44
- Completed: 44
- Remaining: 0

---

## A) Scope and baseline

- [x] `W64-A01` Profile post-Wave-63 hotspots and choose next low-risk high-value split targets.
- [x] `W64-A02` Select Home Assistant tool handlers with multi-branch concentration.
- [x] `W64-A03` Include `home_ha_todo.py` in scope.
- [x] `W64-A04` Include `home_ha_timer.py` in scope.
- [x] `W64-A05` Include `home_media_control_tool.py` in scope.
- [x] `W64-A06` Preserve behavior/audit/policy semantics and existing response text contracts.

## B) Home Assistant to-do split

- [x] `W64-B01` Create `home_ha_todo_preflight.py`.
- [x] `W64-B02` Move policy/config/action/entity/identity/readonly preflight checks.
- [x] `W64-B03` Create `home_ha_todo_list_action.py`.
- [x] `W64-B04` Move list/get-items retrieval and list rendering flow.
- [x] `W64-B05` Create `home_ha_todo_mutate_action.py`.
- [x] `W64-B06` Move add/remove service dispatch + recovery path.
- [x] `W64-B07` Reduce `home_ha_todo.py` to orchestrator wrapper.

## C) Home Assistant timer split

- [x] `W64-C01` Create `home_ha_timer_preflight.py`.
- [x] `W64-C02` Move tool/config/action/entity/identity/readonly checks.
- [x] `W64-C03` Create `home_ha_timer_state_action.py`.
- [x] `W64-C04` Move timer state retrieval and response shaping.
- [x] `W64-C05` Create `home_ha_timer_mutate_action.py`.
- [x] `W64-C06` Move start/pause/cancel/finish duration/service dispatch flow.
- [x] `W64-C07` Reduce `home_ha_timer.py` to orchestrator wrapper.

## D) Home media control split

- [x] `W64-D01` Create `home_media_control_preflight.py`.
- [x] `W64-D02` Move action/entity validation and volume validation.
- [x] `W64-D03` Move identity authorization, area policy, preview checks.
- [x] `W64-D04` Create `home_media_control_execute.py`.
- [x] `W64-D05` Move dry-run response/audit behavior.
- [x] `W64-D06` Move execution/recovery/error mapping behavior.
- [x] `W64-D07` Reduce `home_media_control_tool.py` to orchestrator wrapper.

## E) Import boundaries and verification

- [x] `W64-E01` Extend import-boundary coverage for new to-do split modules.
- [x] `W64-E02` Extend import-boundary coverage for new timer split modules.
- [x] `W64-E03` Extend import-boundary coverage for new media split modules.
- [x] `W64-E04` Run focused lint on all changed modules.
- [x] `W64-E05` Run targeted pytest for `smart_home` + HA todo/timer/media paths.
- [x] `W64-E06` Run `tests/test_import_boundaries.py`.
- [x] `W64-E07` Run full `make check`.
- [x] `W64-E08` Run full `make security-gate`.
- [x] `W64-E09` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W64-F01` Record line-count reductions and extracted module set.
- [x] `W64-F02` Commit Wave 64 tranche.
- [x] `W64-F03` Push Wave 64 to origin/main.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `home_ha_todo.py`: `189 -> 24`
  - `home_ha_timer.py`: `171 -> 24`
  - `home_media_control_tool.py`: `197 -> 19`
- New extracted modules:
  - `home_ha_todo_preflight.py`
  - `home_ha_todo_list_action.py`
  - `home_ha_todo_mutate_action.py`
  - `home_ha_timer_preflight.py`
  - `home_ha_timer_state_action.py`
  - `home_ha_timer_mutate_action.py`
  - `home_media_control_preflight.py`
  - `home_media_control_execute.py`
- Validation status:
  - Focused lint: pass.
  - Targeted pytest (`home_assistant_todo/home_assistant_timer/media_control/smart_home`): `46 passed`.
  - `tests/test_import_boundaries.py`: pass.
  - `make check`: `700 passed`.
  - `make security-gate`: `700 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
