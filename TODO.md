# Jarvis TODO — Wave 73 (HA HTTP + Runtime Persistence Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 35
- Completed: 35
- Remaining: 0

---

## A) Scope and baseline

- [x] `W73-A01` Profile next runtime concentration points after Wave 72.
- [x] `W73-A02` Select `services_ha_http_runtime.py` for split.
- [x] `W73-A03` Select `services_runtime_state_persistence.py` for split.
- [x] `W73-A04` Preserve all existing imports consumed by wrappers/callers.
- [x] `W73-A05` Keep behavior and error-code semantics unchanged.

## B) HA HTTP split

- [x] `W73-B01` Create `services_ha_http_state_runtime.py`.
- [x] `W73-B02` Move `ha_get_state` implementation.
- [x] `W73-B03` Move `ha_get_domain_services` implementation.
- [x] `W73-B04` Create `services_ha_http_actions_runtime.py`.
- [x] `W73-B05` Move `ha_call_service` implementation.
- [x] `W73-B06` Move `ha_get_json` implementation.
- [x] `W73-B07` Move `ha_request_json` implementation.
- [x] `W73-B08` Move `ha_render_template` implementation.
- [x] `W73-B09` Reduce `services_ha_http_runtime.py` to compatibility wrapper.

## C) Runtime persistence split

- [x] `W73-C01` Create `services_runtime_state_serialize_runtime.py`.
- [x] `W73-C02` Move `json_safe_clone` and `replace_state_dict` helpers.
- [x] `W73-C03` Move `expansion_state_payload` implementation.
- [x] `W73-C04` Move `persist_expansion_state` implementation.
- [x] `W73-C05` Create `services_runtime_state_load_runtime.py`.
- [x] `W73-C06` Move `load_expansion_state` implementation.
- [x] `W73-C07` Wire load module to serialize helpers.
- [x] `W73-C08` Reduce `services_runtime_state_persistence.py` to compatibility wrapper.

## D) Boundaries and focused verification

- [x] `W73-D01` Extend import-boundary coverage for HA HTTP split modules.
- [x] `W73-D02` Extend import-boundary coverage for runtime persistence split modules.
- [x] `W73-D03` Run focused lint on changed modules.
- [x] `W73-D04` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W73-D05` Run targeted HA/home/media + expansion-state tests.
- [x] `W73-D06` Run targeted bind/system-status sanity tests.

## E) Full validation and release

- [x] `W73-E01` Run full `make check`.
- [x] `W73-E02` Run full `make security-gate`.
- [x] `W73-E03` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W73-E04` Record wrapper reductions and extracted-module inventory.
- [x] `W73-E05` Commit Wave 73 tranche.
- [x] `W73-E06` Push Wave 73 to `origin/main`.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `services_ha_http_runtime.py`: `270 -> 23`
  - `services_runtime_state_persistence.py`: `287 -> 19`
- New extracted modules:
  - `services_ha_http_state_runtime.py`
  - `services_ha_http_actions_runtime.py`
  - `services_runtime_state_serialize_runtime.py`
  - `services_runtime_state_load_runtime.py`
- Validation status:
  - `uv run pytest -q tests/test_import_boundaries.py`: `165 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "home_assistant or media_control or expansion_state_persists_across_bind or integration_hub_release_channel_actions"`: `26 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "bind_clears_action_history or system_status_reports_snapshot"`: `2 passed`.
  - `make check`: `754 passed`.
  - `make security-gate`: `754 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
