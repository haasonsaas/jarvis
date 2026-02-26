# Security Maintenance

This runbook defines dependency/version policy and monthly maintenance tasks for CI/action supply-chain hygiene.

## 1) Third-Party Workflow Provenance

| Component | Source | Pin/verification strategy |
|---|---|---|
| `actions/checkout` | GitHub (`actions/checkout`) | Full commit SHA pin in workflows |
| `actions/setup-python` | GitHub (`actions/setup-python`) | Full commit SHA pin in workflows |
| `actions/upload-artifact` | GitHub (`actions/upload-artifact`) | Full commit SHA pin in workflows |
| `astral-sh/setup-uv` | Astral (`astral-sh/setup-uv`) | Full commit SHA pin in workflows |
| `github/codeql-action/*` | GitHub (`github/codeql-action`) | Full commit SHA pin in workflows |
| `actionlint` binary | GitHub release (`rhysd/actionlint`) | Version pin + SHA256 checksum verification in workflow |
| `gitleaks` binary | GitHub release (`gitleaks/gitleaks`) | Version pin + SHA256 checksum verification in workflow |
| `shellcheck` | Ubuntu apt repository | Installed from `ubuntu-latest` apt; review version during monthly maintenance |

## 2) Minimum Version Policy (Critical Dependencies)

Keep explicit lower bounds in `pyproject.toml` for core runtime/security-critical dependencies. Raise floors when upstream advisories require it.

| Dependency | Minimum floor policy | Rationale |
|---|---|---|
| `aiohttp` | `>=3.10.0` | Network boundary + HTTP client security fixes |
| `python-dotenv` | `>=1.0.0` | Stable env loading semantics |
| `torch` | `>=2.0.0` | Model runtime compatibility/security updates |
| `ultralytics` | `>=8.3.0` | Vision pipeline compatibility + fixes |
| `faster-whisper` | `>=1.1.0` | STT runtime compatibility |
| `claude-agent-sdk` | `>=0.1.0` | Agent/runtime protocol compatibility |

When adding new critical dependencies:
1. Add an explicit lower bound.
2. Document rationale in this table.
3. Add/update tests for config/runtime fallback behavior when feasible.

## 3) Monthly Maintenance Checklist

Run this once per month:

1. Update action pins:
   - Re-resolve latest trusted SHAs for pinned actions.
   - Update pins in `.github/workflows/*.yml`.
2. Refresh workflow binary pins:
   - `actionlint` version + checksum.
   - `gitleaks` version + checksum.
3. Review dependency updates:
   - Triage open Dependabot PRs.
   - Prioritize security updates and networking/auth libraries.
4. Run security workflows manually:
   - `security.yml` (CodeQL + pip-audit)
   - `secrets-scan.yml` (gitleaks)
5. Validate baseline exceptions:
   - Review `.gitleaksignore` entries.
   - Remove stale/obsolete fingerprints.
6. Confirm docs are current:
   - This runbook
   - `docs/operations/release-checklist.md`
