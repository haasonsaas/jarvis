# Jarvis TODO — Wave 25 (Preview and Ambiguity Runtime Decomposition)

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

- [x] `W25-S01` Extract ambiguity helpers from `services.py` into `src/jarvis/tools/services_preview_runtime.py` (`_tokenized_words`, `_is_ambiguous_high_risk_text`, `_is_ambiguous_entity_target`).
- [x] `W25-S02` Extract preview token workflow helpers (`_plan_preview_signature`, `_prune_plan_previews`, `_issue_plan_preview_token`, `_consume_plan_preview_token`, `_plan_preview_message`, `_preview_gate`) into `services_preview_runtime.py`.
- [x] `W25-S03` Replace extracted helpers in `services.py` with compatibility wrappers for domain modules.

## B) Quality and verification

- [x] `W25-Q01` Re-run targeted preview/ambiguity tests and full `make check`, `make security-gate`, and readiness full suite.

---

## Outcome snapshot (current)

- New preview runtime helper module: `src/jarvis/tools/services_preview_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `1,982` lines (from `2,038` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
