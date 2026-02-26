# Incident Response and Rollback Playbook

## Incident Triggers

- repeated `failure_burst` alerts
- persistent auth/http/network failures for critical integrations
- unexpected destructive action execution
- sensitive data exposure in logs/audit output

## Severity Levels

- Sev-1: active unsafe behavior or data exposure
- Sev-2: major functionality degraded (voice loop/tooling unreliable)
- Sev-3: non-critical degradation with safe fallback available

## Immediate Containment

1. Disable risky surfaces in config:
   - `HOME_PERMISSION_PROFILE=readonly`
   - `NOTIFICATION_PERMISSION_PROFILE=off`
   - `WEBHOOK_INBOUND_ENABLED=false`
2. If needed, stop runtime and preserve artifacts:
   - `~/.jarvis/audit.jsonl*`
   - observability DB/event logs
3. Record timeline and impacted components.

## Technical Triage

1. Query `system_status` and capture `health`, `integrations`, `observability`, `voice_attention`.
2. Review recent tool executions (`tool_summary`, `tool_summary_text`).
3. Review operator actions and inbound webhook events.
4. Correlate with `failure_burst`, watchdog resets, and fallback events.

## Rollback Procedure

1. Identify last known-good commit.
2. Roll back deployment to known-good version.
3. Re-run validation gates:
   - `make check`
   - `make test-faults`
4. Confirm smoke checks in sim mode:
   - startup
   - voice turn
   - read-only tool path (`system_status`)
5. Re-enable integrations in stages.

## Post-Incident

- Add/expand regression tests for the failed path.
- Update runbooks and alert thresholds.
- Document root cause, remediation, and follow-up owner/date.
