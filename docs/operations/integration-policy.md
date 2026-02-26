# External Integration Policy Layers

This runbook covers operational setup and policy behavior for Todoist and Pushover integrations.

## 1) Feature Availability
- Tools are always registered, but runtime behavior depends on configuration and policy profile.
- Missing credentials produce explicit `missing_config` failures.

## 2) Todoist

### Required environment
- `TODOIST_API_TOKEN` (required for all Todoist calls)
- `TODOIST_PROJECT_ID` (optional: scope list/add to a project)
- `TODOIST_PERMISSION_PROFILE=readonly|control`
- `TODOIST_TIMEOUT_SEC` (optional: request timeout in seconds, default `10.0`)

### Tool behavior by profile
- `readonly`
  - allows: `todoist_list_tasks`
  - denies: `todoist_add_task`
- `control`
  - allows both list and add

### Runtime notes
- `todoist_add_task` requires `content`.
- `todoist_add_task` validates:
  - `priority` must be integer `1..4`
  - `labels` must be a list of non-empty strings
- `todoist_list_tasks` accepts optional `limit`.
- `todoist_list_tasks` supports `format=short|verbose`.
- Invalid upstream payloads are normalized as `invalid_json`.

## 3) Pushover

### Required environment
- `PUSHOVER_API_TOKEN`
- `PUSHOVER_USER_KEY`
- `NOTIFICATION_PERMISSION_PROFILE=off|allow`
- `PUSHOVER_TIMEOUT_SEC` (optional: request timeout in seconds, default `10.0`)

### Tool behavior by profile
- `off`: denies `pushover_notify`
- `allow`: allows `pushover_notify`

### Runtime notes
- `pushover_notify` requires `message`.
- `pushover_notify` validates `priority` as integer `-2..2`.
- API-level rejects (`status=0`) are normalized as `api_error`.
- Malformed payloads are normalized as `invalid_json`.

## 4) Diagnostics
- `system_status` includes:
  - `todoist_configured`
  - `pushover_configured`
  - policy snapshot for todoist/notification profiles

## 5) Audit Location, Rotation, and Redaction Guarantees
- Audit path: `~/.jarvis/audit.jsonl`
- Rotation settings:
  - `AUDIT_LOG_MAX_BYTES` default is `1000000`
  - `AUDIT_LOG_BACKUPS` default is `3`
  - Backups roll as `audit.jsonl.1` through `audit.jsonl.N`
- Todoist and Pushover audits intentionally store metadata-only summaries.
- Smart-home payload data is redacted by sensitive key token matching before audit write (`token`, `secret`, `code`, `pin`, `password`, etc.).
- Redacted values are persisted as `***REDACTED***`.
- Todoist/Pushover metadata-only enforcement drops raw body fields before write (`content`, `description`, `due_string`, `message`, `title`).

### Metadata-only examples

Input attempt (internal tool details):
```json
{
  "result": "ok",
  "content": "my password is swordfish",
  "description": "private context",
  "content_length": 24
}
```

Persisted audit details:
```json
{
  "result": "ok",
  "content_length": 24
}
```

## 6) Troubleshooting Matrix

| Symptom | Likely cause | Operator action |
|---|---|---|
| `Todoist not configured. Set TODOIST_API_TOKEN.` | Missing/empty `TODOIST_API_TOKEN` | Set token in `.env` and restart process |
| `Todoist authentication failed. Check TODOIST_API_TOKEN.` | Invalid or revoked Todoist token | Rotate token and retest with `todoist_list_tasks` |
| `Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY.` | One or both Pushover fields are missing | Set both values and restart process |
| `Notification policy blocks pushover_notify` (tool denied) | `NOTIFICATION_PERMISSION_PROFILE=off` | Switch to `allow` if operationally approved |
| `Todoist policy blocks todoist_add_task` (tool denied) | `TODOIST_PERMISSION_PROFILE=readonly` | Switch to `control` for write access |
| `invalid_json` result from Todoist/Pushover path | Upstream payload shape changed or transient invalid response | Retry once, then inspect API response and update parser tests |
| Repeated `http_error` / `network_client_error` | Upstream outage, DNS, connectivity, or timeout issue | Validate network path, check service status page, rerun `make test-faults` |

## 7) Triage Flow
1. Check credential env vars are set and non-empty.
2. Check profile env vars:
   - `TODOIST_PERMISSION_PROFILE`
   - `NOTIFICATION_PERMISSION_PROFILE`
3. Run `system_status` and verify configured/profile fields.
4. Run `make test-faults` for fast taxonomy and error-path regression validation.

## 8) Local Productivity Timers
- `timer_create` accepts numeric seconds or compact durations (`90s`, `5m`, `1h 15m`).
- `timer_list` reports current active timers and remaining time.
- `timer_cancel` removes a timer by `timer_id` or exact `label`.
- Timers are persisted in the memory store when memory is enabled and are restored on restart.

## 9) Local Productivity Reminders
- `reminder_create` accepts:
  - epoch seconds
  - ISO datetime
  - compact relative due values (`in 15m`, `45m`, `1h 30m`)
- `reminder_list` shows pending reminders and due/overdue status; `include_completed=true` includes completed entries.
- `reminder_complete` marks a pending reminder completed by `reminder_id`.
- `reminder_notify_due` dispatches due reminder notifications through Pushover and marks reminders as notified to prevent duplicates.
- Reminders are persisted in the memory store when memory is enabled.

## 10) Home Assistant Calendar Bridge
- `calendar_events` reads events from Home Assistant calendars in a caller-defined window.
- `calendar_next_event` returns the next upcoming calendar event in the selected window.
- Optional `calendar_entity_id` scopes reads to one calendar; otherwise all available calendars are queried.

## 11) Home Assistant To-Do/Timer/Area Helpers
- `home_assistant_todo` supports:
  - `action=list` (read path)
  - `action=add|remove` (write path, blocked in `HOME_PERMISSION_PROFILE=readonly`)
- `home_assistant_timer` supports:
  - `action=state` (read path)
  - `action=start|pause|cancel|finish` (write path, blocked in `readonly`)
- `home_assistant_area_entities` provides area-aware entity resolution for room-targeted planning.
- `media_control` provides a safer media abstraction for `media_player` entities:
  - supported actions: `play`, `pause`, `turn_on`, `turn_off`, `toggle`, `mute`, `unmute`, `volume_set`
  - `volume_set` validates `volume` in `[0.0, 1.0]`

## 12) Weather
- `weather_lookup` uses Open-Meteo geocoding + forecast APIs.
- `WEATHER_UNITS=metric|imperial` controls default response units.
- Runtime request timeout is controlled by `WEATHER_TIMEOUT_SEC`.

## 13) Webhooks (Outbound)
- `webhook_trigger` enforces:
  - `https` URLs only
  - host matching against `WEBHOOK_ALLOWLIST` (exact host or subdomain match)
- Optional auth injection:
  - if `WEBHOOK_AUTH_TOKEN` is set and no `Authorization` header is provided, the tool adds `Authorization: Bearer <token>`.
- Runtime request timeout defaults to `WEBHOOK_TIMEOUT_SEC`.

## 14) Slack/Discord Channel Hooks
- `slack_notify` posts to `SLACK_WEBHOOK_URL`.
- `discord_notify` posts to `DISCORD_WEBHOOK_URL`.
- Channel hooks are opt-in and follow `NOTIFICATION_PERMISSION_PROFILE`:
  - `off`: deny channel sends
  - `allow`: permit channel sends

## 15) Integration Health Snapshot
- `system_status` includes an `integrations` block with current configuration state for:
  - `home_assistant`
  - `todoist`
  - `pushover`
  - `weather`
  - `webhook`
  - `channels`
- `system_status_contract` includes `integrations_required` for automation consumers.

## 16) Status Contract for Automation
- `system_status` includes `schema_version` for machine consumers.
- `system_status_contract` returns required top-level sections and nested required keys used by automation checks.
