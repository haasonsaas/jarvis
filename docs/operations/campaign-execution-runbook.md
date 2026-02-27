# Reliability Campaign Execution Runbook

## Scope

Defines standard soak/fault campaign cadence, command set, and artifact retention.

## Standard Cadence

- Daily: quick signal
  - `./scripts/test_soak_campaign.sh fast 1`
  - `./scripts/test_fault_campaign.sh quick 1`
- Pre-release: medium campaign
  - `make test-soak-campaign`
  - `make test-fault-campaign`
- Release candidate: extended campaign
  - `./scripts/test_soak_campaign.sh live 2`
  - `./scripts/test_fault_campaign.sh all 2`

## Artifact Contract

- Soak campaign artifacts:
  - `.artifacts/quality/soak-campaign-<profile>-repeat<repeat>.json`
- Fault campaign artifacts:
  - `.artifacts/quality/fault-campaign-<profile-set>-repeat<repeat>.json`
- Keep artifacts for trend analysis and regression comparison.

## Review Checklist

1. Verify `accepted=true`.
2. Verify `failed_count=0` and expected phase count matches profile plan.
3. Confirm no repeated fault-profile regressions in `stdout_tail`/`stderr_tail`.
4. Record campaign ID and artifact paths in release notes.

## Escalation

- If any campaign fails, block release promotion.
- Run incident playbooks:
  - `incident-response.md`
  - `integrations-degradation-runbook.md`
  - `autonomy-checkpoint-runbook.md`
