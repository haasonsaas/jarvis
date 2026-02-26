# Error Taxonomy Reference

Canonical tool error taxonomy shared by service tools and telemetry.

## Ownership by Tool Family

| Error code | Owning tool families |
|---|---|
| `api_error` | `pushover_notify` |
| `auth` | `smart_home`, `smart_home_state`, `todoist_*`, `pushover_notify` |
| `cancelled` | `smart_home*`, `todoist_*`, `pushover_notify` |
| `http_error` | `smart_home*`, `todoist_*`, `pushover_notify` |
| `invalid_data` | `smart_home`, `task_plan_*`, `memory_*` |
| `invalid_json` | `smart_home*`, `todoist_*`, `pushover_notify` |
| `invalid_plan` | `task_plan_*` |
| `invalid_status` | `task_plan_update` |
| `invalid_steps` | `task_plan_create` |
| `missing_config` | `smart_home*`, `todoist_*`, `pushover_notify` |
| `missing_entity` | `smart_home_state` |
| `missing_fields` | `smart_home`, `todoist_add_task`, `pushover_notify` |
| `missing_plan` | `task_plan_*` |
| `missing_query` | `memory_search` |
| `missing_store` | `memory_*`, `task_plan_*` |
| `missing_text` | `memory_add` |
| `network_client_error` | `smart_home*`, `todoist_*`, `pushover_notify` |
| `not_found` | `smart_home*`, `task_plan_*` |
| `policy` | cross-cutting tool policy enforcement |
| `storage_error` | `memory_*`, `task_plan_*` |
| `summary_unavailable` | `tool_summary*`, `system_status` |
| `timeout` | `smart_home*`, `todoist_*`, `pushover_notify` |
| `unexpected` | cross-cutting runtime guard |
| `unknown_error` | fallback normalization bucket |

## Canonical Code Set (Machine-Checked)

Do not edit this list without updating `src/jarvis/tool_errors.py` and tests.

<!-- SERVICE_ERROR_CODES_START -->
api_error
auth
cancelled
http_error
invalid_data
invalid_json
invalid_plan
invalid_status
invalid_steps
missing_config
missing_entity
missing_fields
missing_plan
missing_query
missing_store
missing_text
network_client_error
not_found
policy
storage_error
summary_unavailable
timeout
unexpected
unknown_error
<!-- SERVICE_ERROR_CODES_END -->
