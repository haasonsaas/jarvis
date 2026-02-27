# Jarvis TODO — Wave 19 (Home Assistant Runtime Decomposition)

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

- [x] `W19-S01` Extract Home Assistant HTTP helper implementations from `services.py` into `src/jarvis/tools/services_ha_runtime.py`.
- [x] `W19-S02` Replace `_ha_get_state`, `_ha_get_domain_services`, `_ha_call_service`, `_ha_get_json`, `_ha_request_json`, and `_ha_render_template` in `services.py` with compatibility wrappers that delegate to runtime helpers.
- [x] `W19-S03` Preserve compatibility dependency surfaces expected by domain modules (`services.aiohttp`) after extraction.

## B) Behavioral parity

- [x] `W19-B01` Keep extracted helper semantics consistent with prior behavior (error codes, status mappings, payload handling), including `_ha_render_template` (`invalid_json`, `not_found`, raw text passthrough).

## C) Quality and verification

- [x] `W19-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New HA runtime helper module: `src/jarvis/tools/services_ha_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,817` lines (from `2,997` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
