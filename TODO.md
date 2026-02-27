# Jarvis TODO — Wave 62 (Hotspot Decomposition Sweep II)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 47
- Completed: 47
- Remaining: 0

---

## A) Scope and baseline

- [x] `W62-A01` Confirm post-Wave-61 baseline and capture next highest concentration service-domain modules.
- [x] `W62-A02` Select targeted split scope for next tranche.
- [x] `W62-A03` Include `home_mutation_preflight.py` in scope.
- [x] `W62-A04` Include `integrations_calendar.py` in scope.
- [x] `W62-A05` Include `integrations_webhook_trigger.py` in scope.
- [x] `W62-A06` Include `governance_skills_governance.py` in scope.
- [x] `W62-A07` Preserve public behavior and response text contracts.
- [x] `W62-A08` Preserve monkeypatch/test seam compatibility for service-level helpers.

## B) Home mutation preflight split

- [x] `W62-B01` Create `home_mutation_policy.py`.
- [x] `W62-B02` Move identity/policy/safety checks into policy module.
- [x] `W62-B03` Move area-policy and preview-gate checks into policy module.
- [x] `W62-B04` Create `home_mutation_state_checks.py`.
- [x] `W62-B05` Move cooldown and HA state preflight checks into state module.
- [x] `W62-B06` Keep no-op short-circuit logic unchanged.
- [x] `W62-B07` Reduce `home_mutation_preflight.py` to orchestrator wrapper.

## C) Calendar split

- [x] `W62-C01` Create `integrations_calendar_common.py`.
- [x] `W62-C02` Move calendar event fetch utility.
- [x] `W62-C03` Move calendar window parsing utility.
- [x] `W62-C04` Centralize calendar error-code to response mapping.
- [x] `W62-C05` Create `integrations_calendar_events_list.py`.
- [x] `W62-C06` Move `calendar_events` flow.
- [x] `W62-C07` Create `integrations_calendar_next.py`.
- [x] `W62-C08` Move `calendar_next_event` flow.
- [x] `W62-C09` Reduce `integrations_calendar.py` to compat exports.
- [x] `W62-C10` Restore service-level monkeypatch seam for `_calendar_fetch_events` in split handlers.

## D) Webhook trigger split

- [x] `W62-D01` Create `integrations_webhook_trigger_preflight.py`.
- [x] `W62-D02` Move webhook policy/allowlist/identity/preview checks.
- [x] `W62-D03` Move timeout/header/request setup into preflight context.
- [x] `W62-D04` Create `integrations_webhook_trigger_execute.py`.
- [x] `W62-D05` Move webhook execution/recovery/dead-letter paths.
- [x] `W62-D06` Keep response semantics and audit behavior unchanged.
- [x] `W62-D07` Reduce `integrations_webhook_trigger.py` to thin orchestrator.

## E) Skills governance split

- [x] `W62-E01` Create `governance_skills_actions_a.py`.
- [x] `W62-E02` Move negotiation and dependency health actions.
- [x] `W62-E03` Create `governance_skills_actions_b.py`.
- [x] `W62-E04` Move quota set/get/check actions.
- [x] `W62-E05` Create `governance_skills_actions_c.py`.
- [x] `W62-E06` Move harness/bundle_sign/sandbox_template actions.
- [x] `W62-E07` Reduce `governance_skills_governance.py` to dispatcher.

## F) Import boundaries and quality gates

- [x] `W62-F01` Add import-boundary coverage for new home mutation split modules.
- [x] `W62-F02` Add import-boundary coverage for new calendar split modules.
- [x] `W62-F03` Add import-boundary coverage for new webhook split modules.
- [x] `W62-F04` Add import-boundary coverage for new skills governance split modules.
- [x] `W62-F05` Run focused lint across all changed modules.
- [x] `W62-F06` Run targeted pytest coverage for calendar/webhook/skills paths.
- [x] `W62-F07` Run `tests/test_import_boundaries.py`.
- [x] `W62-F08` Run full `make check`.
- [x] `W62-F09` Run full `make security-gate`.

## G) Release loop

- [x] `W62-G01` Record line-count deltas for split wrapper modules.
- [x] `W62-G02` Commit Wave 62 tranche.
- [x] `W62-G03` Push Wave 62 to origin/main.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `home_mutation_preflight.py`: `263 -> 18`
  - `integrations_calendar.py`: `240 -> 17`
  - `integrations_webhook_trigger.py`: `232 -> 30`
  - `governance_skills_governance.py`: `217 -> 60`
- New extracted modules:
  - `home_mutation_policy.py`
  - `home_mutation_state_checks.py`
  - `integrations_calendar_common.py`
  - `integrations_calendar_events_list.py`
  - `integrations_calendar_next.py`
  - `integrations_webhook_trigger_preflight.py`
  - `integrations_webhook_trigger_execute.py`
  - `governance_skills_actions_a.py`
  - `governance_skills_actions_b.py`
  - `governance_skills_actions_c.py`
- Behavioral compatibility note:
  - Calendar split handlers continue to resolve `_calendar_fetch_events` via `jarvis.tools.services` to preserve existing test and monkeypatch seam behavior.
