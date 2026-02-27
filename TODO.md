# Jarvis TODO — Wave 9 (Services Decomposition Continuation)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 9
- Completed: 9
- Remaining: 0

---

## A) Service decomposition

- [x] `W9-S01` Extract `weather_lookup` from `services.py` into a domain module.
- [x] `W9-S02` Extract `webhook_trigger` from `services.py` into a domain module.
- [x] `W9-S03` Extract calendar helpers (`_calendar_fetch_events`, `_parse_calendar_window`) into a domain module.
- [x] `W9-S04` Extract `calendar_events` from `services.py` into a domain module.
- [x] `W9-S05` Extract `calendar_next_event` from `services.py` into a domain module.
- [x] `W9-S06` Rewire `services.py` imports and preserve compatibility shim for tests monkeypatching `_calendar_fetch_events`.
- [x] `W9-S07` Extract `media_control` into `services_domains/home.py`.
- [x] `W9-S08` Extract Home Assistant conversation/todo/timer/area handlers into `services_domains/home.py`.
- [x] `W9-S09` Extract `smart_home` into `services_domains/home.py`.

## B) Quality and verification

- [x] `W9-Q01` Re-run targeted service and lifecycle suites.
- [x] `W9-Q02` Re-run full `make check`, `make security-gate`, readiness, and strict eval dataset.

---

## Outcome snapshot (current)

- `services.py` reduced from `8,890` lines to `7,278` lines in this wave.
- `services_domains/integrations.py` now owns weather/webhook/calendar runtime handlers.
- `services_domains/home.py` now owns smart-home/media/conversation/todo/timer/area runtime handlers.
- Strict eval contract remains green at `91/91`.
- Full test suite remains green (`555 passed`).
