# Jarvis TODO — Wave 27 (Policy and Guest Session Runtime Decomposition)

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

- [x] `W27-S01` Extract nudge/quiet-hours policy helpers from `services.py` into `src/jarvis/tools/services_policy_runtime.py` (`_normalize_nudge_policy`, `_hhmm_to_minutes`, `_quiet_window_active`).
- [x] `W27-S02` Extract identity profile + guest-session lifecycle helpers into `services_policy_runtime.py` (`_identity_profile_level`, `_profile_rank`, `_prune_guest_sessions`, `_resolve_guest_session`, `_register_guest_session`).
- [x] `W27-S03` Replace extracted functions in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W27-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New policy runtime helper module: `src/jarvis/tools/services_policy_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `1,884` lines (from `1,933` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
