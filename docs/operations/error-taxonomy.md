# Error Taxonomy Reference

Canonical tool error taxonomy shared by service tools and telemetry.

## Ownership by Tool Family

| Error code | Owning tool families |
|---|---|
| `api_error` | `pushover_notify`, `reminder_notify_due` |
| `auth` | `smart_home`, `smart_home_state`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `slack_notify`, `discord_notify`, `email_send`, `webhook_trigger` |
| `cancelled` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `slack_notify`, `discord_notify`, `weather_lookup`, `webhook_trigger` |
| `circuit_open` | integrations guarded by circuit breaker (`home_assistant*`, `todoist_*`, `pushover_notify`, `weather_lookup`, `webhook_trigger`, `slack_notify`, `discord_notify`, `email_send`) |
| `http_error` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `slack_notify`, `discord_notify`, `weather_lookup`, `webhook_trigger` |
| `invalid_data` | `smart_home`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `media_control`, `weather_lookup`, `webhook_trigger`, `timer_*`, `reminder_*`, `calendar_*`, `task_plan_*`, `memory_*` |
| `invalid_json` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `weather_lookup` |
| `invalid_plan` | `task_plan_*` |
| `invalid_status` | `task_plan_update` |
| `invalid_steps` | `task_plan_create` |
| `missing_config` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `slack_notify`, `discord_notify`, `email_send`, `reminder_notify_due` |
| `missing_entity` | `smart_home_state`, `home_assistant_capabilities` |
| `missing_fields` | `smart_home`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `weather_lookup`, `webhook_trigger`, `timer_cancel`, `reminder_create`, `reminder_complete`, `todoist_add_task`, `pushover_notify`, `slack_notify`, `discord_notify`, `email_send` |
| `missing_plan` | `task_plan_*` |
| `missing_query` | `memory_search` |
| `missing_store` | `memory_*`, `task_plan_*` |
| `missing_text` | `memory_add` |
| `network_client_error` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `slack_notify`, `discord_notify`, `email_send`, `weather_lookup`, `webhook_trigger` |
| `not_found` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `timer_cancel`, `reminder_complete`, `task_plan_*`, `calendar_*` |
| `policy` | cross-cutting tool policy enforcement (`smart_home*`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `media_control`, `slack_notify`, `discord_notify`, `email_send`, `memory_add` PII guardrails, `webhook_trigger`, `reminder_notify_due`, allow/deny lists) |
| `storage_error` | `memory_*`, `task_plan_*`, `timer_*`, `reminder_*` |
| `summary_unavailable` | `tool_summary*`, `system_status` |
| `timeout` | `smart_home*`, `home_assistant_capabilities`, `home_assistant_conversation`, `home_assistant_todo`, `home_assistant_timer`, `home_assistant_area_entities`, `calendar_*`, `todoist_*`, `pushover_notify`, `slack_notify`, `discord_notify`, `weather_lookup`, `webhook_trigger` |
| `unexpected` | cross-cutting runtime guard |
| `unknown_error` | fallback normalization bucket |

## Canonical Code Set (Machine-Checked)

Do not edit this list without updating `src/jarvis/tool_errors.py` and tests.

<!-- SERVICE_ERROR_CODES_START -->
api_error
auth
cancelled
circuit_open
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
