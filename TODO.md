# Jarvis TODO — Wave 24 (Memory Runtime Decomposition)

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

- [x] `W24-S01` Extract memory scope/policy helpers from `services.py` into `src/jarvis/tools/services_memory_runtime.py` (`_normalize_memory_scope`, `_memory_scope_tag`, `_memory_scope_from_tags`, `_infer_memory_scope`, `_memory_scope_for_add`, `_memory_scope_tags`, `_memory_visible_tags`, `_memory_entry_scope`, `_memory_policy_scopes_for_query`, `_memory_requested_scopes`).
- [x] `W24-S02` Extract memory confidence/source helpers and expansion response helpers (`_memory_confidence_score`, `_memory_confidence_label`, `_memory_source_trail`, `_json_payload_response`, `_expansion_payload_response`) into `services_memory_runtime.py`.
- [x] `W24-S03` Replace extracted functions in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W24-Q01` Re-run targeted memory/trust tests and full `make check`, `make security-gate`, and readiness full suite.

---

## Outcome snapshot (current)

- New memory runtime helper module: `src/jarvis/tools/services_memory_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,038` lines (from `2,088` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
