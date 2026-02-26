# Release Checklist

Use this checklist for policy or integration behavior changes before merging to `main` and before deploying to a live robot environment.

## 1) Pre-merge Validation

- [ ] `make check` passes locally.
- [ ] `make test-faults` passes locally.
- [ ] New/changed policy behavior has test coverage for:
  - allow path
  - deny path
  - failure normalization path
- [ ] `TODO.md` items touched in this release are updated (`[x]` / `[ ]`) to reflect current status.
- [ ] Any new GitHub Action usage is pinned to a full commit SHA.

## 2) Configuration Review

- [ ] Required environment variables for changed integrations are documented in `README.md`.
- [ ] Permission profiles are explicitly reviewed:
  - `HOME_PERMISSION_PROFILE`
  - `TODOIST_PERMISSION_PROFILE`
  - `NOTIFICATION_PERMISSION_PROFILE`
- [ ] Defaults are still safe for first boot (`readonly`/`off` where applicable).
- [ ] Startup warning behavior remains accurate for incomplete configs.

## 3) Audit and Safety Review

- [ ] Audit output verified at `~/.jarvis/audit.jsonl`.
- [ ] Sensitive fields are redacted in audit records (`***REDACTED***`).
- [ ] Audit rotation tested or confirmed:
  - `AUDIT_LOG_MAX_BYTES`
  - `AUDIT_LOG_BACKUPS`
- [ ] Destructive smart-home actions still require `confirm=true` where expected.
- [ ] Dry-run paths (`dry_run=true`) were exercised before execute paths.

## 4) CI and Workflow Health

- [ ] `ci.yml` completes (`lint`, `tests`, and `faults` when applicable).
- [ ] `workflow-sanity.yml` completes (actionlint + script checks).
- [ ] `shellcheck.yml` completes for shell script changes.
- [ ] `security.yml` has no new actionable CodeQL alerts for changed files.
- [ ] Artifacts are present for test diagnostics:
  - junit XML
  - optional coverage XML (if manually requested)

## 5) Rollout Steps

1. Merge to `main` only after all required checks pass.
2. Deploy and run an initial startup in simulation mode:
   - `uv run python -m jarvis --sim --no-vision`
3. Execute a low-risk live smoke test:
   - read-only status path (`system_status`)
   - integration read path (`todoist_list_tasks` if configured)
   - smart-home dry-run path (if Home Assistant configured)
4. Validate audit log writes for the smoke-test actions.

## 6) Rollback Triggers and Actions

Trigger rollback when any of the following occur:
- Repeated `auth`, `http_error`, or `network_client_error` in a newly changed path.
- Incorrect allow/deny policy behavior versus documented profiles.
- Sensitive content appears in audit output.

Rollback actions:
1. Revert the release commit(s) from `main`.
2. Re-run `make check` and `make test-faults`.
3. Redeploy previous known-good revision.
4. Capture incident notes and add missing regression tests before retrying release.
