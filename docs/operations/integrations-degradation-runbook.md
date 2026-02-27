# Integrations Degradation Runbook

## Scope

Use this runbook when external integrations degrade or flap:
- Home Assistant / webhook / messaging failures
- repeated circuit-breaker opens
- dead-letter queue growth

## Detect and Classify

1. Inspect integration health:
   - `system_status` (integration and circuit-breaker sections)
   - `integration_hub` health/status actions
2. Inspect recent failures:
   - `tool_summary`
   - `dead_letter_list`

## Containment

1. Reduce external surface area:
   - disable optional channels first (Slack/Discord/Pushover/webhook outbound)
2. Keep core local capabilities online:
   - preserve read-only status tools and local memory/status inspection

## Recovery

1. Recover connectivity/auth issues per integration:
   - rotate credentials or endpoint config
2. Replay backlog incrementally:
   - `dead_letter_replay` with small limits
3. Confirm breaker recovery:
   - verify circuit state transitions from open to healthy in `system_status`

## Release Channel Fallback

1. If regression suspected, move to stable release controls:
   - set integration release policy via `integration_hub`
2. Re-run smoke checks for affected integrations.
3. Promote back only after stable pass window.

## Exit Criteria

- breaker state healthy for critical integrations
- dead-letter queue drained or bounded with known remaining items
- release channel posture documented and verified
