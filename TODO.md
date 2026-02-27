# Jarvis TODO — Wave 11 (Services Decomposition Continuation)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 6
- Completed: 6
- Remaining: 0

---

## A) Service decomposition

- [x] `W11-S01` Extract memory runtime handlers (`memory_add`, `memory_update`, `memory_forget`, `memory_search`, `memory_status`, `memory_recent`, `memory_summary_add`, `memory_summary_list`) into `services_domains/trust.py`.
- [x] `W11-S02` Extract inbound webhook inbox handlers (`webhook_inbound_list`, `webhook_inbound_clear`) into `services_domains/integrations.py`.
- [x] `W11-S03` Extract dead-letter queue handlers (`dead_letter_list`, `dead_letter_replay`) into `services_domains/integrations.py`.
- [x] `W11-S04` Extract tool summary handlers (`tool_summary`, `tool_summary_text`) into `services_domains/governance.py`.
- [x] `W11-S05` Break out service schema/permission constant blocks from `services.py` into dedicated modules to reduce top-level load.

## B) Quality and verification

- [x] `W11-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after Wave 11 extraction items complete.

---

## Outcome snapshot (current)

- `services.py` is now `4,699` lines (down from `5,974` before Wave 11 and `8,890` before Waves 9-11).
- `services_domains/trust.py` now owns proactive + identity + memory-governance + memory runtime handlers.
- `services_domains/integrations.py` now owns inbound webhook queue inspection + dead-letter replay/list handlers.
- `services_domains/governance.py` now owns tool summary runtime handlers in addition to skills/status/quality handlers.
- `services.py` now imports `SERVICE_TOOL_SCHEMAS` + `SERVICE_RUNTIME_REQUIRED_FIELDS` from the new `service_schemas.py` module.
- Full gates are green: `make check` (`555 passed`), `make security-gate`, and readiness full (`91/91` strict eval).
