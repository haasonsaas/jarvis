# Jarvis Engineering TODO (Research-Grounded Execution Backlog)

Last updated: 2026-02-26

This backlog is intentionally extensive (50+ items) and is based on a fresh research pass of:
- `openclaw/openclaw` workflow patterns (`ci.yml`, `workflow-sanity.yml`)
- `home-assistant/core` CI orchestration patterns (`ci.yaml`)
- current local repo architecture, tests, and CI layout

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

---

## 1) Safety and Policy Layer (10 items)

- [ ] `S01` Restrict mutating `smart_home` to an explicit domain allowlist; deny unknown domains by default.
- [ ] `S02` Add tests that unknown mutating domains are rejected before any HTTP request.
- [ ] `S03` Expand sensitive-domain set with policy rationale and tests.
- [ ] `S04` Normalize `domain` and `entity_id` inputs (trim/lower) before comparisons.
- [ ] `S05` Add tests for mixed-case + whitespace domain/entity inputs.
- [ ] `S06` Add explicit validation for empty/invalid `action` strings with normalized `invalid_data`.
- [ ] `S07` Add optional stricter mode for requiring `confirm=true` on all non-dry-run actions.
- [ ] `S08` Add tests for stricter confirm mode branches.
- [ ] `S09` Add policy diagnostics in `system_status` for strict-confirm mode.
- [ ] `S10` Add a policy decision trace field in audit records (`allowed|denied|dry_run`).

Files: `src/jarvis/tools/services.py`, `src/jarvis/config.py`, `tests/test_tools.py`, `tests/test_config.py`

---

## 2) External Integration Reliability (10 items)

- [ ] `I01` Add bounded retry for `todoist_list_tasks` on transient network/timeout errors.
- [ ] `I02` Add jitter/backoff helper and tests for retry timing logic (unit-level, not sleep-heavy).
- [ ] `I03` Add explicit invalid-data checks for Todoist `labels` type/entries.
- [ ] `I04` Add explicit invalid-data checks for Todoist `priority` type/range before HTTP.
- [ ] `I05` Add explicit invalid-data checks for Pushover `priority` type/range before HTTP.
- [ ] `I06` Add optional default timeout env vars for Todoist/Pushover requests.
- [ ] `I07` Add config normalization and warnings for invalid timeout env var values.
- [ ] `I08` Add tests for timeout env var fallback behavior.
- [ ] `I09` Add richer list output formatting option (short vs verbose) for Todoist task listing.
- [ ] `I10` Add tests for short/verbose list formatting modes.

Files: `src/jarvis/tools/services.py`, `src/jarvis/config.py`, `tests/test_tools.py`, `tests/test_config.py`

---

## 3) Audit and Privacy Hardening (8 items)

- [ ] `A01` Expand sensitive key redaction aliases (`alarm_code`, `passcode`, `webhook_id`, `oauth_token`).
- [ ] `A02` Add regression tests for all new redaction aliases across nested objects/lists.
- [ ] `A03` Add audit schema helper to enforce metadata-only fields for notification/task integrations.
- [ ] `A04` Add cross-tool test verifying no raw message/content/title fields leak into audits.
- [ ] `A05` Add tests for audit rotation when existing backups already exist at max count.
- [ ] `A06` Add tests for rotation error handling when backup rename/unlink fails.
- [ ] `A07` Add system_status field exposing audit redaction mode enabled/disabled.
- [ ] `A08` Add doc update with redaction examples in runbooks.

Files: `src/jarvis/tools/services.py`, `tests/test_tools.py`, `docs/operations/home-control-policy.md`, `docs/operations/integration-policy.md`

---

## 4) Telemetry and Taxonomy (8 items)

- [ ] `T01` Add taxonomy reference doc with each error code and owning tool families.
- [ ] `T02` Add test asserting taxonomy doc examples stay in sync with constants.
- [ ] `T03` Track unknown summary detail count in telemetry snapshot.
- [ ] `T04` Add tests for unknown summary detail accounting.
- [ ] `T05` Add explicit counter for per-code service error totals in telemetry snapshot.
- [ ] `T06` Add tests for per-code aggregation stability.
- [ ] `T07` Add NaN/inf guard tests for telemetry averages.
- [ ] `T08` Add startup log line summarizing taxonomy sizes (service/storage subsets).

Files: `src/jarvis/tool_errors.py`, `src/jarvis/__main__.py`, `tests/test_main_lifecycle.py`, `docs/operations/error-taxonomy.md`

---

## 5) CI and Workflow Evolution (12 items)

- [x] `C01` Add docs-only change detection gate to skip test/fault jobs when safe.
- [x] `C02` Add changed-scope filtering for path groups (services/tests/docs/workflows).
- [x] `C03` Add `workflow_dispatch` inputs to CI for `lint-only`, `faults-only`, and `full`.
- [ ] `C04` Add optional coverage XML generation in CI (non-blocking artifact).
- [x] `C05` Upload junit/pytest artifacts for easier failure triage.
- [x] `C06` Add job-level timeout values for CI jobs to prevent hangs.
- [x] `C07` Pin `actions/*` usages to full commit SHA (supply-chain hardening).
- [ ] `C08` Add a lightweight workflow to validate shell scripts (`shellcheck`) on PRs.
- [ ] `C09` Add a security workflow (`codeql` or equivalent) with weekly schedule.
- [x] `C10` Add dependency update automation (`dependabot` config) for Python and GitHub Actions.
- [ ] `C11` Add a CI summary step that reports slowest tests.
- [x] `C12` Add explicit CI check for executable bit + shebang consistency in scripts.

Files: `.github/workflows/ci.yml`, `.github/workflows/workflow-sanity.yml`, `.github/dependabot.yml`, `scripts/`

---

## 6) Test Architecture and Maintainability (8 items)

- [x] `Q01` Introduce shared `aiohttp` mock helpers in `tests/conftest.py`.
- [x] `Q02` Refactor representative service tests to use shared HTTP helpers.
- [x] `Q03` Refactor remaining duplicated HTTP mock blocks to shared helpers.
- [ ] `Q04` Parametrize timeout/cancelled/network error tests across integrations.
- [x] `Q05` Add taxonomy-to-fault-selector contract test.
- [ ] `Q06` Add helper assertions for audit payload structure to reduce repeated code.
- [ ] `Q07` Split very long `tests/test_tools.py` into thematic modules.
- [ ] `Q08` Add marker strategy for fast/slow/fault tests and document usage.

Files: `tests/conftest.py`, `tests/test_tools.py`, `tests/test_*.py`

---

## 7) Documentation and Runbooks (8 items)

- [x] `D01` Create external integrations runbook (Todoist/Pushover policy + troubleshooting).
- [x] `D02` Update home-control runbook with redaction and cooldown semantics.
- [x] `D03` Reconcile architecture diagram MCP/tool labels with current capabilities.
- [ ] `D04` Add runbook section for CI workflow intent and failure routing.
- [ ] `D05` Add operator checklist for first-time env setup validation.
- [ ] `D06` Add troubleshooting matrix mapping common errors to likely fixes.
- [ ] `D07` Add short section on audit location/rotation/redaction guarantees.
- [ ] `D08` Add release checklist doc for safe rollout of policy changes.

Files: `README.md`, `docs/operations/home-control-policy.md`, `docs/operations/integration-policy.md`, `docs/operations/release-checklist.md`

---

## 8) Security and Dependency Hygiene (6 items)

- [ ] `H01` Add `pip-audit` (or equivalent) CI step on schedule and PR.
- [ ] `H02` Add secret scanning pre-commit/CI step and baseline handling.
- [ ] `H03` Add provenance notes for third-party actions/tools in workflows.
- [ ] `H04` Add policy for minimum pinned versions of critical dependencies.
- [ ] `H05` Add tests for config warnings on insecure/empty auth-like env combinations.
- [ ] `H06` Add monthly maintenance task list for dependency and workflow pin refresh.

Files: `.github/workflows/*.yml`, `pyproject.toml`, `README.md`, `docs/operations/security-maintenance.md`, `tests/test_config.py`

---

## 9) Immediate Execution Queue

- [x] `E01` Execute `C03` (manual workflow dispatch inputs and branch-safe toggles).
- [x] `E02` Execute `Q03` (finish HTTP helper refactor sweep).
- [x] `E03` Execute `Q05` (fault selector taxonomy contract test).
- [x] `E04` Execute `D03` (README architecture sync).
- [x] `E05` Execute `C07` (pin GitHub actions by SHA).
