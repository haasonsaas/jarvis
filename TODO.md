# Jarvis TODO — Wave 6 (Service Decomposition + Eval Expansion)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 16
- Completed: 16
- Remaining: 0

---

## A) Service decomposition

- [x] `W6-S01` Create domain package `src/jarvis/tools/services_domains`.
- [x] `W6-S02` Extract `home_orchestrator` into `services_domains/home.py`.
- [x] `W6-S03` Extract `planner_engine` into `services_domains/planner.py`.
- [x] `W6-S04` Extract `integration_hub` into `services_domains/integrations.py`.
- [x] `W6-S05` Extract comms handlers (`slack/discord/email/todoist/pushover`) into `services_domains/comms.py`.
- [x] `W6-S06` Rewire `services.py` imports to use domain handlers.
- [x] `W6-S07` Keep MCP tool names/schemas and public behavior unchanged after extraction.
- [x] `W6-S08` Reduce `services.py` line count significantly (from 11,472 to 9,660).

## B) Eval coverage

- [x] `W6-E01` Expand `docs/evals/assistant-contract.json` from 2 cases to 50+.
- [x] `W6-E02` Add planner/autonomy coverage cases (schedule/checkpoint/cycle/status).
- [x] `W6-E03` Add home orchestration + automation pipeline coverage cases.
- [x] `W6-E04` Add integration hub + release-channel coverage cases.
- [x] `W6-E05` Add comms/integration channel coverage cases.
- [x] `W6-E06` Keep strict eval acceptance green (`--strict --min-pass-rate 1.0 --max-failed 0`).

## C) Documentation + verification

- [x] `W6-D01` Update README structure to reflect domain modules.
- [x] `W6-D02` Validate with full local gates (`make check`, `make security-gate`, `jarvis_readiness.sh full`).

---

## Remaining for this wave

All Wave 6 items are implemented and validated.
