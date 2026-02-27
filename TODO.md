# Jarvis TODO — Wave 4 (Provider Execution + Automation + Autonomy)

Last updated: 2026-02-27

This wave focused on three requested outcomes:
1. real provider-backed `integration_hub` execution paths,
2. Home Assistant automation create/apply/rollback pipeline with dry-run diff,
3. long-horizon autonomy scheduling with explicit safety checkpoints.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 30
- Completed: 30
- Remaining: 0

---

## A) Provider-Backed Integration Execution

- [x] `W4-I01` Replace `integration_hub` calendar upsert draft-only flow with executable Home Assistant path.
- [x] `W4-I02` Replace `integration_hub` calendar delete draft-only flow with executable Home Assistant path.
- [x] `W4-I03` Keep safe draft fallback for calendar actions when Home Assistant is unavailable.
- [x] `W4-I04` Add calendar payload normalization for all-day vs datetime event fields.
- [x] `W4-I05` Upgrade `integration_hub` messaging send phase to actually dispatch by channel.
- [x] `W4-I06` Wire messaging send dispatch to existing channel tools (`slack_notify`, `discord_notify`, `email_send`, `pushover_notify`).
- [x] `W4-I07` Return delivery tool/result metadata from messaging flows.
- [x] `W4-I08` Add optional Notion-backed notes capture execution path.
- [x] `W4-I09` Keep notes backend graceful fallback when Notion credentials are not configured.
- [x] `W4-I10` Extend integration schema fields for calendar/message execution inputs.

## B) Home Assistant Automation Pipeline

- [x] `W4-H01` Add automation draft store (`automation_create`) in `home_orchestrator`.
- [x] `W4-H02` Add normalized automation config validation (`alias`, `trigger`, `actions`).
- [x] `W4-H03` Add dry-run diff preview for automation apply (`automation_apply`, `dry_run=true`).
- [x] `W4-H04` Add confirmed apply path (`dry_run=false`, `confirm=true`).
- [x] `W4-H05` Add HA-native config apply helper with method fallback and reload.
- [x] `W4-H06` Add local-only apply toggle (`ha_apply=false`) for simulation/testing workflows.
- [x] `W4-H07` Add rollback preview path (`automation_rollback`, `dry_run=true`).
- [x] `W4-H08` Add rollback execute path with confirmation and HA/local support.
- [x] `W4-H09` Add automation status/query endpoint (`automation_status`) for draft/applied states.
- [x] `W4-H10` Persist automation drafts/applied states across restarts.

## C) Long-Horizon Autonomy Loop + Safety Checkpoints

- [x] `W4-A01` Add autonomy scheduling action (`autonomy_schedule`) in `planner_engine`.
- [x] `W4-A02` Add per-task risk + checkpoint policy metadata on scheduled autonomy tasks.
- [x] `W4-A03` Add explicit checkpoint update action (`autonomy_checkpoint`).
- [x] `W4-A04` Add autonomy cycle runner (`autonomy_cycle`) that executes due tasks.
- [x] `W4-A05` Block high/medium risk due tasks when checkpoints are missing.
- [x] `W4-A06` Add recurring autonomy task support via `recurrence_sec`.
- [x] `W4-A07` Feed executed autonomy tasks into proactive follow-through queue.
- [x] `W4-A08` Add autonomy status/health summary action (`autonomy_status`).
- [x] `W4-A09` Persist autonomy checkpoints + cycle history across restarts.
- [x] `W4-A10` Expose autonomy counts in expansion/system status snapshots.

## D) Runtime/Config/Documentation/Test Coverage

- [x] `W4-R01` Add Notion config fields (`NOTION_API_TOKEN`, `NOTION_DATABASE_ID`) to config model.
- [x] `W4-R02` Add startup warning for partially-configured Notion credentials.
- [x] `W4-R03` Update `.env.example` for Notion integration settings.
- [x] `W4-R04` Update README for new integration/orchestration/autonomy capabilities.
- [x] `W4-R05` Add integration tests for executable calendar/messaging flows.
- [x] `W4-R06` Add orchestration tests for automation create/apply/rollback/status.
- [x] `W4-R07` Add planner tests for checkpoint-gated autonomy cycle execution.
- [x] `W4-R08` Keep readiness and regression suite green after all changes.

---

## Remaining for this wave

All requested items for this wave are implemented and validated.
