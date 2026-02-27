# Jarvis TODO — Wave 70 (HA + Integrations + Schedule Runtime Decomposition)

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

- [x] `W70-A01` Profile next runtime hotspots after Wave 69.
- [x] `W70-A02` Select `services_ha_runtime.py` for split.
- [x] `W70-A03` Select `services_integrations_runtime.py` for split.
- [x] `W70-A04` Select `services_schedule_runtime.py` for split.
- [x] `W70-A05` Preserve all imports consumed by `services.py`.

## B) Home Assistant runtime split

- [x] `W70-B01` Create `services_ha_http_runtime.py`.
- [x] `W70-B02` Move HA request/state/service/template helpers.
- [x] `W70-B03` Create `services_ha_response_runtime.py`.
- [x] `W70-B04` Move `ha_conversation_speech` response extraction helper.
- [x] `W70-B05` Reduce `services_ha_runtime.py` to compatibility wrapper.

## C) Integrations runtime split

- [x] `W70-C01` Create `services_integrations_release_runtime.py`.
- [x] `W70-C02` Move release-channel config/check evaluation helpers.
- [x] `W70-C03` Move quality-report artifact writer helper.
- [x] `W70-C04` Create `services_integrations_notes_runtime.py`.
- [x] `W70-C05` Move local/obsidian note capture helper.
- [x] `W70-C06` Move Notion capability/config + async bridge helper.
- [x] `W70-C07` Reduce `services_integrations_runtime.py` to compatibility wrapper.

## D) Schedule runtime split

- [x] `W70-D01` Create `services_schedule_parse_runtime.py`.
- [x] `W70-D02` Move duration/datetime parsing and formatting helpers.
- [x] `W70-D03` Create `services_schedule_state_runtime.py`.
- [x] `W70-D04` Move timer/reminder ID allocation and status helpers.
- [x] `W70-D05` Move persisted timer/reminder load helpers.
- [x] `W70-D06` Reduce `services_schedule_runtime.py` to compatibility wrapper.

## E) Boundaries and validation

- [x] `W70-E01` Extend import-boundary coverage for HA split modules.
- [x] `W70-E02` Extend import-boundary coverage for integrations split modules.
- [x] `W70-E03` Extend import-boundary coverage for schedule split modules.
- [x] `W70-E04` Run focused lint on changed runtime files.
- [x] `W70-E05` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W70-E06` Run targeted tools tests covering HA/integrations/schedule paths.
- [x] `W70-E07` Run full `make check`.
- [x] `W70-E08` Run full `make security-gate`.
- [x] `W70-E09` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W70-F01` Record wrapper reduction deltas and extracted module counts.
- [x] `W70-F02` Commit Wave 70 tranche.
- [x] `W70-F03` Push Wave 70 tranche to `origin/main`.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `services_ha_runtime.py`: `289 -> 23`
  - `services_integrations_runtime.py`: `252 -> 25`
  - `services_schedule_runtime.py`: `273 -> 37`
- New extracted modules:
  - `services_ha_http_runtime.py`
  - `services_ha_response_runtime.py`
  - `services_integrations_release_runtime.py`
  - `services_integrations_notes_runtime.py`
  - `services_schedule_parse_runtime.py`
  - `services_schedule_state_runtime.py`
- Validation status:
  - `uv run pytest -q tests/test_import_boundaries.py`: `153 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "home_assistant or media_control or integration_hub_release_channel_actions or expansion_state_persists_across_bind or timer_ or reminder_ or calendar_ or webhook_"`: `49 passed`.
  - `make check`: `742 passed`.
  - `make security-gate`: `742 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
