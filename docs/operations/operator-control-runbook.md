# Operator Control Incident Runbook

## Scope

Use this runbook when operator auth or control-plane behavior is degraded:
- unexpected operator write actions
- auth mode drift (`observe`/`standard`/`strict`) or risk mismatch
- repeated unauthorized control attempts

## Immediate Containment

1. Reduce operator blast radius:
   - set operator auth mode to `strict`
   - disable non-essential integrations if incident involves external calls
2. Capture current control state and recent actions:
   - `system_status`
   - `tool_summary`
   - `tool_summary_text`
3. Preserve artifacts:
   - `~/.jarvis/audit.jsonl*`
   - observability DB/event log snapshots

## Triage Procedure

1. Verify auth and trust posture:
   - `system_status` (check `operator_auth`, `risk`, `identity`)
   - `identity_trust` (verify requester profile/session posture)
2. Confirm whether unsafe actions were preview-gated:
   - inspect `plan_preview` and strict confirmation fields in status payload
3. Correlate timeline:
   - operator server events (`/events`)
   - recent tool records (`tool_summary`, `tool_summary_text`)

## Rollback Procedure

1. Revoke temporary guest sessions and elevated approvals:
   - terminate guest capability windows via `identity_trust`
2. Reapply known-good operator config:
   - restore expected auth mode and control preset
3. Validate safe behavior:
   - run read-only checks (`system_status`, `jarvis_scorecard`)
   - run one controlled mutating preview flow and verify explicit ack is required

## Exit Criteria

- operator auth mode and risk signals stable for one observation window
- no unauthorized actions in recent audit timeline
- alert stream clear of control-plane anomalies
