# Home Control Policy Layers

This project uses multiple control layers for Home Assistant actions.

## 1) Feature Toggle
- `HOME_ENABLED=true|false`
- When `false`, both `smart_home` and `smart_home_state` tools are disabled.

## 2) Permission Profile
- `HOME_PERMISSION_PROFILE=readonly|control`
- `readonly`: denies mutating `smart_home` actions, allows `smart_home_state`.
- `control`: allows both tools, subject to policy checks below.

## 2.5) Identity and Trust Overlay
- Optional identity enforcement layer:
  - `IDENTITY_ENFORCEMENT_ENABLED=true`
  - `IDENTITY_USER_PROFILES` (`user=deny|readonly|control|trusted`)
- Per-user policy is layered over global home policy.
- User-level identity cannot elevate globally denied behavior (for example global `HOME_PERMISSION_PROFILE=readonly` still blocks writes).
- High-risk actions can require approval through:
  - `approval_code` (matching `IDENTITY_APPROVAL_CODE`), or
  - trusted requester path (`approved=true` with trusted identity).

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

For `home_assistant_todo` requests:
- `action` must be one of `list`, `add`, `remove`.
- `list` is read-only and permitted in both profiles.
- `add`/`remove` are blocked when `HOME_PERMISSION_PROFILE=readonly`.

For `home_assistant_timer` requests:
- `action` must be one of `state`, `start`, `pause`, `cancel`, `finish`.
- `state` is read-only and always permitted.
- `start`/`pause`/`cancel`/`finish` are blocked when `HOME_PERMISSION_PROFILE=readonly`.
- `start` accepts `duration` as `HH:MM:SS` or compact duration (`5m`, `90s`, `1h 15m`).

For `home_assistant_area_entities` requests:
- Read-only helper for area-aware planning.
- Resolves entities via Home Assistant template function `area_entities()`.
- Optional domain filter narrows entity classes (for example `light`, `switch`).

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

## HA Intent Rollout Checklist
1. Start with `HOME_PERMISSION_PROFILE=readonly`.
2. Keep `HOME_CONVERSATION_ENABLED=false` until entity inventory and permissions are validated.
3. Validate area mappings with `home_assistant_area_entities` for each active room.
4. Validate safe command plans with `home_assistant_capabilities` before execute flows.
5. Exercise non-mutating paths first:
   - `smart_home_state`
   - `home_assistant_todo` with `action=list`
   - `home_assistant_timer` with `action=state`
6. If conversational control is needed:
   - set `HOME_CONVERSATION_ENABLED=true`
   - set `HOME_CONVERSATION_PERMISSION_PROFILE=control`
   - require `confirm=true` in every call.
7. Enable `HOME_REQUIRE_CONFIRM_EXECUTE=true` for shared/household deployments.
8. Audit review: inspect `~/.jarvis/audit.jsonl` for redaction and expected policy decisions before moving to production.

## Troubleshooting
- If actions are denied unexpectedly:
  1. Check `HOME_ENABLED`.
  2. Check `HOME_PERMISSION_PROFILE`.
  3. Ensure sensitive executes pass `confirm=true`.
  4. Verify `HASS_URL` and `HASS_TOKEN` are both set.
  5. If an execute is blocked, check whether an action cooldown is currently active.
  6. For `home_assistant_conversation`, verify `HOME_CONVERSATION_ENABLED=true`, `HOME_CONVERSATION_PERMISSION_PROFILE=control`, and `confirm=true`.
