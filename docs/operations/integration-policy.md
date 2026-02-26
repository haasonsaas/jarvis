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

### Tool behavior by profile
- `readonly`
  - allows: `todoist_list_tasks`
  - denies: `todoist_add_task`
- `control`
  - allows both list and add

### Runtime notes
- `todoist_add_task` requires `content`.
- `todoist_list_tasks` accepts optional `limit`.
- Invalid upstream payloads are normalized as `invalid_json`.

## 3) Pushover

### Required environment
- `PUSHOVER_API_TOKEN`
- `PUSHOVER_USER_KEY`
- `NOTIFICATION_PERMISSION_PROFILE=off|allow`

### Tool behavior by profile
- `off`: denies `pushover_notify`
- `allow`: allows `pushover_notify`

### Runtime notes
- `pushover_notify` requires `message`.
- API-level rejects (`status=0`) are normalized as `api_error`.
- Malformed payloads are normalized as `invalid_json`.

## 4) Diagnostics
- `system_status` includes:
  - `todoist_configured`
  - `pushover_configured`
  - policy snapshot for todoist/notification profiles

## 5) Security and Audit
- Todoist and Pushover audits intentionally store metadata only.
- Smart-home service payloads are sensitive-key redacted before audit write.

## 6) Troubleshooting
1. Check credential env vars are set and non-empty.
2. Check profile env vars:
   - `TODOIST_PERMISSION_PROFILE`
   - `NOTIFICATION_PERMISSION_PROFILE`
3. Run `system_status` and verify configured/profile fields.
4. Run `make test-faults` for fast taxonomy and error-path regression validation.
