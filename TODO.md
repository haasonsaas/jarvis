# Jarvis TODO — Wave 23 (Schedule and Datetime Runtime Decomposition)

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

- [x] `W23-S01` Extract scheduling and datetime helper chain from `services.py` into `src/jarvis/tools/services_schedule_runtime.py` (`_duration_seconds`, `_local_timezone`, `_parse_datetime_text`, `_parse_due_timestamp`, `_timestamp_to_iso_utc`, `_format_duration`).
- [x] `W23-S02` Extract timer/reminder ID allocation and runtime state helpers (`_allocate_timer_id`, `_allocate_reminder_id`, `_prune_timers`, `_timer_status`, `_load_timers_from_store`, `_reminder_status`, `_load_reminders_from_store`) into `services_schedule_runtime.py`.
- [x] `W23-S03` Replace extracted helpers in `services.py` with compatibility wrappers.

## B) Quality and verification

- [x] `W23-Q01` Run targeted timer/reminder/calendar tests after extraction.
- [x] `W23-Q02` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New schedule runtime helper module: `src/jarvis/tools/services_schedule_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,088` lines (from `2,282` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
