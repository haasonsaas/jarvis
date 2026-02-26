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
