# Jarvis TODO — Wave 29 (Action Cooldown Runtime Decomposition)

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

- [x] `W29-S01` Extract retry/backoff helper from `services.py` into `src/jarvis/tools/services_action_runtime.py` (`_retry_backoff_delay`).
- [x] `W29-S02` Extract action cooldown/history helpers into `services_action_runtime.py` (`_action_key`, `_prune_action_history`, `_cooldown_active`, `_touch_action`).
- [x] `W29-S03` Replace extracted helpers in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W29-Q01` Re-run targeted cooldown/retry checks and full `make check`, `make security-gate`, and readiness full suite.

---

## Outcome snapshot (current)

- New action runtime helper module: `src/jarvis/tools/services_action_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `1,773` lines (from `1,785` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
