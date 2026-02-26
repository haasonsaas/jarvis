# Identity and Trust Policy

This runbook defines requester identity handling, per-user permission layering, and approval flow for high-risk actions.

## 1) Identity Inputs
- `requester_id`: explicit caller identity for a tool request.
- `request_context`: optional object that may include `requester_id`/`user_id` and `speaker_verified`.
- `speaker_verified`: trusted-speaker hook for voice pipelines.

Resolution order:
1. `requester_id`
2. `request_context.requester_id` or `request_context.user_id`
3. `IDENTITY_DEFAULT_USER`

## 2) Configuration
- `IDENTITY_ENFORCEMENT_ENABLED=false|true`
- `IDENTITY_DEFAULT_USER` (default: `owner`)
- `IDENTITY_DEFAULT_PROFILE=deny|readonly|control|trusted`
- `IDENTITY_USER_PROFILES` (comma list: `user=profile`)
- `IDENTITY_TRUSTED_USERS` (comma list)
- `IDENTITY_REQUIRE_APPROVAL=false|true`
- `IDENTITY_APPROVAL_CODE` (optional shared approval code)

## 3) Permission Profiles
- `deny`: blocks all mutating/high-impact operations for that requester.
- `readonly`: allows read paths, blocks mutating actions.
- `control`: normal operator permissions.
- `trusted`: control permissions plus trusted approval path.

## 4) Precedence Model
1. Global tool/home/integration policy gates run first.
2. Identity profile restrictions are applied on top.
3. User profile cannot elevate a globally denied capability.

Examples:
- If `HOME_PERMISSION_PROFILE=readonly`, a requester with `control` still cannot execute HA writes.
- If requester profile is `deny`, mutating integrations are blocked even when global policy allows.

## 5) High-Risk Approval Handshake
For high-risk tools (for example `webhook_trigger`, `email_send`, `home_assistant_conversation`):
- Allowed when `IDENTITY_REQUIRE_APPROVAL=false`.
- When approval is required, allow if either:
  - `approval_code` matches `IDENTITY_APPROVAL_CODE`, or
  - requester is trusted and request sets `approved=true`.

Recommended practice:
- Keep `IDENTITY_REQUIRE_APPROVAL=true` in shared environments.
- Use a long rotated `IDENTITY_APPROVAL_CODE` (8+ chars minimum).
- Keep `IDENTITY_TRUSTED_USERS` minimal.

## 6) Denied-Action Guidance
Policy denials return actionable user guidance:
- profile updates: “ask an admin to update `IDENTITY_USER_PROFILES`”
- readonly escalation: “ask a trusted user or admin to execute this action”
- approval failures: “provide `approval_code` or trusted `approved=true` path”

## 7) Audit Fields
Audit entries include identity metadata:
- `requester_id`
- `requester_profile`
- `requester_trusted`
- `speaker_verified`
- `identity_source`
- `decision_chain`

This supports post-incident reason tracing for authorization decisions.

## 8) Operational Checks
1. Validate configuration:
   - run with `--sim` and inspect startup warnings.
2. Validate status:
   - run `system_status` and inspect `identity` and `tool_policy` sections.
3. Validate enforcement:
   - test one denied request (`deny` profile)
   - test one readonly-denied mutation
   - test one high-risk approval success path.
