# Jarvis TODO — Wave 61 (Five Hotspot Decomposition Sweep)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 40
- Completed: 40
- Remaining: 0

---

## A) Scope and baseline

- [x] `W61-A01` Confirm baseline and identify remaining highest-concentration service-domain modules.
- [x] `W61-A02` Select 5-module hotspot sweep:
- [x] `W61-A03` `home_orch_automation.py`
- [x] `W61-A04` `home_ha_conversation.py`
- [x] `W61-A05` `comms_notify_webhooks.py`
- [x] `W61-A06` `planner_engine_autonomy.py`
- [x] `W61-A07` `trust_memory_query.py`
- [x] `W61-A08` Preserve public function contracts and existing behavior/messages.

## B) Home automation split

- [x] `W61-B01` Create `home_orch_automation_suggest_create.py`.
- [x] `W61-B02` Move `home_orch_automation_suggest`.
- [x] `W61-B03` Move `home_orch_automation_create`.
- [x] `W61-B04` Create `home_orch_automation_apply_status.py`.
- [x] `W61-B05` Move `home_orch_automation_apply`.
- [x] `W61-B06` Move `home_orch_automation_rollback`.
- [x] `W61-B07` Move `home_orch_automation_status`.
- [x] `W61-B08` Reduce `home_orch_automation.py` to exports.

## C) Conversation split

- [x] `W61-C01` Create `home_ha_conversation_preflight.py`.
- [x] `W61-C02` Move policy/guard/preview checks.
- [x] `W61-C03` Create `home_ha_conversation_execute.py`.
- [x] `W61-C04` Move HA conversation request/response handling.
- [x] `W61-C05` Reduce `home_ha_conversation.py` to orchestrator wrapper.

## D) Notifications split

- [x] `W61-D01` Create `comms_notify_slack.py`.
- [x] `W61-D02` Move `slack_notify`.
- [x] `W61-D03` Create `comms_notify_discord.py`.
- [x] `W61-D04` Move `discord_notify`.
- [x] `W61-D05` Reduce `comms_notify_webhooks.py` to exports.

## E) Planner autonomy split

- [x] `W61-E01` Create `planner_engine_autonomy_schedule_checkpoint.py`.
- [x] `W61-E02` Move `planner_autonomy_schedule`.
- [x] `W61-E03` Move `planner_autonomy_checkpoint`.
- [x] `W61-E04` Create `planner_engine_autonomy_cycle.py`.
- [x] `W61-E05` Move `planner_autonomy_cycle`.
- [x] `W61-E06` Create `planner_engine_autonomy_status.py`.
- [x] `W61-E07` Move `planner_autonomy_status`.
- [x] `W61-E08` Reduce `planner_engine_autonomy.py` to exports.

## F) Trust memory query split

- [x] `W61-F01` Create `trust_memory_search.py`.
- [x] `W61-F02` Move `memory_search`.
- [x] `W61-F03` Create `trust_memory_recent.py`.
- [x] `W61-F04` Move `memory_recent`.
- [x] `W61-F05` Create `trust_memory_status_view.py`.
- [x] `W61-F06` Move `memory_status`.
- [x] `W61-F07` Reduce `trust_memory_query.py` to exports.

## G) Boundaries and validation

- [x] `W61-G01` Extend import-boundary coverage for all newly extracted modules.
- [x] `W61-G02` Run focused lint for all changed modules.
- [x] `W61-G03` Run targeted pytest for affected behavior clusters.
- [x] `W61-G04` Run `tests/test_import_boundaries.py`.
- [x] `W61-G05` Run full `make check`.
- [x] `W61-G06` Run full `make security-gate`.
- [x] `W61-G07` Run `./scripts/jarvis_readiness.sh fast`.

## H) Release loop

- [x] `W61-H01` Record post-split line-count outcomes.
- [x] `W61-H02` Commit Wave 61.
- [x] `W61-H03` Push Wave 61.

---

## Outcome snapshot (completed)

- Five hotspot modules decomposed to facades/wrappers:
  - `home_orch_automation.py`: `288 -> 21`
  - `home_ha_conversation.py`: `268 -> 30`
  - `comms_notify_webhooks.py`: `257 -> 8`
  - `planner_engine_autonomy.py`: `254 -> 17`
  - `trust_memory_query.py`: `243 -> 9`
- New extracted modules (selected):
  - `home_orch_automation_suggest_create.py` (`99`)
  - `home_orch_automation_apply_status.py` (`204`)
  - `home_ha_conversation_preflight.py` (`172`)
  - `home_ha_conversation_execute.py` (`140`)
  - `comms_notify_slack.py` (`133`)
  - `comms_notify_discord.py` (`138`)
  - `planner_engine_autonomy_schedule_checkpoint.py` (`121`)
  - `planner_engine_autonomy_cycle.py` (`115`)
  - `planner_engine_autonomy_status.py` (`46`)
  - `trust_memory_search.py` (`134`)
  - `trust_memory_recent.py` (`72`)
  - `trust_memory_status_view.py` (`59`)
- Validation status:
  - Focused lint: pass.
  - Focused pytest clusters: pass.
  - `tests/test_import_boundaries.py`: `85 passed`.
  - `make check`: `674 passed`.
  - `make security-gate`: `674 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
