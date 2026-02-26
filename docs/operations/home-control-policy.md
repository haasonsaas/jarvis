# Home Control Policy Layers

This project uses multiple control layers for Home Assistant actions.

## 1) Feature Toggle
- `HOME_ENABLED=true|false`
- When `false`, both `smart_home` and `smart_home_state` tools are disabled.

## 2) Permission Profile
- `HOME_PERMISSION_PROFILE=readonly|control`
- `readonly`: denies mutating `smart_home` actions, allows `smart_home_state`.
- `control`: allows both tools, subject to policy checks below.

## 3) Runtime Safety Policy
For `smart_home` requests:
- `domain`, `action`, and `entity_id` are required.
- `entity_id` domain must match `domain`.
- Known domain/action pairs are validated before execution.
- Sensitive domains (`lock`, `alarm_control_panel`, `cover`, `climate`) require:
  - `dry_run=false`
  - `confirm=true`
- Rationale:
  - `lock`, `alarm_control_panel`, `cover`: physical security and access impact.
  - `climate`: safety/comfort impact and higher blast radius in shared spaces.
- Optional strict mode: `HOME_REQUIRE_CONFIRM_EXECUTE=true` requires `confirm=true` for every non-dry-run execute, regardless of domain.
- Idempotency short-circuits:
  - `turn_on` returns no-op if already on.
  - `turn_off` returns no-op if already off.

For `home_assistant_conversation` requests:
- Requires `HOME_CONVERSATION_ENABLED=true`.
- Requires `HOME_CONVERSATION_PERMISSION_PROFILE=control`.
- Requires tool argument `confirm=true` on every request.

For `home_assistant_capabilities` requests:
- Read-only helper that fetches current entity state and available domain services.
- Requires `entity_id`.

## 4) Transport/Service Validation
- Preflight state read checks entity existence and auth before mutation.
- Request outcomes are normalized into telemetry error taxonomy.

## 5) Audit and Diagnostics
- All smart-home actions are audit logged.
- Service payloads are sensitive-key redacted before audit persistence (`code`, `pin`, `token`, `secret`, `alarm_code`, `passcode`, `webhook_id`, `oauth_token`, etc.).
- `system_status` includes:
  - tool allow/deny counts
  - active `home_permission_profile`
  - active `home_conversation_enabled`
  - active `home_conversation_permission_profile`

### Redaction examples
Input payload:
```json
{
  "code": "1234",
  "nested": {"alarm_code": "0000", "brightness": 10},
  "callbacks": [{"webhook_id": "hook-1"}, {"safe": "ok"}]
}
```

Audit payload:
```json
{
  "code": "***REDACTED***",
  "nested": {"alarm_code": "***REDACTED***", "brightness": 10},
  "callbacks": [{"webhook_id": "***REDACTED***"}, {"safe": "ok"}]
}
```

## 6) Cooldown Semantics
- Cooldown applies to mutating executes (`dry_run=false`) only.
- Dry-run requests do not consume cooldown history and can be repeated for planning/confirmation.

## Recommended Profiles
- Development: `HOME_PERMISSION_PROFILE=readonly`
- Trusted local automation: `HOME_PERMISSION_PROFILE=control`

## Troubleshooting
- If actions are denied unexpectedly:
  1. Check `HOME_ENABLED`.
  2. Check `HOME_PERMISSION_PROFILE`.
  3. Ensure sensitive executes pass `confirm=true`.
  4. Verify `HASS_URL` and `HASS_TOKEN` are both set.
  5. If an execute is blocked, check whether an action cooldown is currently active.
  6. For `home_assistant_conversation`, verify `HOME_CONVERSATION_ENABLED=true`, `HOME_CONVERSATION_PERMISSION_PROFILE=control`, and `confirm=true`.
