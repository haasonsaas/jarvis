# Jarvis TODO — Wave 11 (Services Decomposition Continuation)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 6
- Completed: 1
- Remaining: 5

---

## A) Service decomposition

- [x] `W11-S01` Extract memory runtime handlers (`memory_add`, `memory_update`, `memory_forget`, `memory_search`, `memory_status`, `memory_recent`, `memory_summary_add`, `memory_summary_list`) into `services_domains/trust.py`.
- [ ] `W11-S02` Extract inbound webhook inbox handlers (`webhook_inbound_list`, `webhook_inbound_clear`) into `services_domains/integrations.py`.
- [ ] `W11-S03` Extract dead-letter queue handlers (`dead_letter_list`, `dead_letter_replay`) into `services_domains/integrations.py`.
- [ ] `W11-S04` Extract tool summary handlers (`tool_summary`, `tool_summary_text`) into `services_domains/governance.py`.
- [ ] `W11-S05` Break out service schema/permission constant blocks from `services.py` into dedicated modules to reduce top-level load.

## B) Quality and verification

- [ ] `W11-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after Wave 11 extraction items complete.

---

## Outcome snapshot (current)

- `services.py` is now `5,636` lines (down from `5,974` before Wave 11).
- `services_domains/trust.py` now owns proactive + identity + memory-governance + memory runtime handlers.
- Full test suite remains green (`555 passed`), security gate passes, and readiness full suite remains green (`91/91` strict eval).
