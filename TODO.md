# Jarvis TODO — Wave 72 (Service Schema Domain Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 35
- Completed: 35
- Remaining: 0

---

## A) Scope and baseline

- [x] `W72-A01` Profile next non-runtime concentration point after Wave 71.
- [x] `W72-A02` Select `service_schemas.py` for schema decomposition.
- [x] `W72-A03` Preserve `SERVICE_TOOL_SCHEMAS` API consumed by `services.py` and `services_server.py`.
- [x] `W72-A04` Preserve `SERVICE_RUNTIME_REQUIRED_FIELDS` contract consumed by tests/callers.
- [x] `W72-A05` Keep JSON-schema parity behavior stable.

## B) Home schema split

- [x] `W72-B01` Create `service_schemas_home.py`.
- [x] `W72-B02` Move home/media-oriented schema entries into home module constant.
- [x] `W72-B03` Preserve high-risk confirmation/identity schema fields for home tools.
- [x] `W72-B04` Preserve required-field declarations for home/media tools.
- [x] `W72-B05` Ensure module imports remain lightweight and isolated.

## C) Comms/integration schema split

- [x] `W72-C01` Create `service_schemas_comms.py`.
- [x] `W72-C02` Move weather/webhook/notifications/email/dead-letter schemas.
- [x] `W72-C03` Move timers/reminders/calendar/todoist/pushover/get_time/status schemas.
- [x] `W72-C04` Preserve integer/number field declarations used by schema tests.
- [x] `W72-C05` Preserve required-field declarations for communication and scheduling tools.

## D) Memory/advanced schema split

- [x] `W72-D01` Create `service_schemas_memory.py`.
- [x] `W72-D02` Move memory/task-plan/tool-summary/skills baseline schemas.
- [x] `W72-D03` Create `service_schemas_advanced.py`.
- [x] `W72-D04` Move proactive/governance/orchestrator/planner/embodiment/integration-hub schemas.
- [x] `W72-D05` Preserve action-field contracts for advanced orchestration domains.

## E) Aggregation and contracts

- [x] `W72-E01` Reduce `service_schemas.py` to wrapper + domain aggregation.
- [x] `W72-E02` Build `SERVICE_TOOL_SCHEMAS` by stable ordered merge of domain fragments.
- [x] `W72-E03` Generate `SERVICE_RUNTIME_REQUIRED_FIELDS` from each schema `required` list.
- [x] `W72-E04` Preserve parity semantics for tools with empty/omitted required fields.
- [x] `W72-E05` Ensure no caller-side API changes.

## F) Validation and release

- [x] `W72-F01` Extend import-boundary coverage for new schema modules.
- [x] `W72-F02` Run focused schema parity/integer/identity field tests.
- [x] `W72-F03` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W72-F04` Run full `make check`.
- [x] `W72-F05` Run full `make security-gate`.
- [x] `W72-F06` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W72-F07` Record concentration reduction and module inventory.
- [x] `W72-F08` Commit and push Wave 72.

---

## Outcome snapshot (completed)

- Wrapper concentration reduction:
  - `service_schemas.py`: `783 -> 35`
- New extracted modules:
  - `service_schemas_home.py`
  - `service_schemas_comms.py`
  - `service_schemas_memory.py`
  - `service_schemas_advanced.py`
- Validation status:
  - `uv run pytest -q tests/test_tools_services.py -k "service_schema_runtime_required_fields_parity or service_schema_integer_fields_are_declared_integer or service_schema_identity_fields_present_for_mutating_tools"`: `3 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "service_schema or system_status_contract_reports_expected_fields"`: `4 passed`.
  - `uv run pytest -q tests/test_import_boundaries.py`: `161 passed`.
  - `make check`: `750 passed`.
  - `make security-gate`: `750 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
