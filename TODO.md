# Jarvis TODO — Wave 57 (Skills Governance Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 24
- Completed: 24
- Remaining: 0

---

## A) Scope and baseline

- [x] `W57-A01` Re-profile largest remaining governance modules after Wave 56.
- [x] `W57-A02` Select `services_domains/governance_skills.py` for decomposition.
- [x] `W57-A03` Preserve API contract for `skills_governance`, `skills_list`, `skills_enable`, `skills_disable`, `skills_version`.

## B) Decomposition design

- [x] `W57-B01` Extract skills-governance action router to `governance_skills_governance.py`.
- [x] `W57-B02` Extract skill-registry lifecycle handlers to `governance_skills_registry.py`.
- [x] `W57-B03` Keep `governance_skills.py` as export facade.

## C) Extraction implementation

- [x] `W57-C01` Create `services_domains/governance_skills_governance.py`.
- [x] `W57-C02` Move negotiate/dependency/quota/harness/bundle/sandbox logic.
- [x] `W57-C03` Preserve helper `_skills_snapshot_rows` in governance action module.
- [x] `W57-C04` Create `services_domains/governance_skills_registry.py`.
- [x] `W57-C05` Move `skills_list` implementation.
- [x] `W57-C06` Move `skills_enable` and `skills_disable` implementations.
- [x] `W57-C07` Move `skills_version` implementation.
- [x] `W57-C08` Replace `governance_skills.py` with thin exports.

## D) Boundaries and quality

- [x] `W57-D01` Add import-boundary check for `governance_skills_governance`.
- [x] `W57-D02` Add import-boundary check for `governance_skills_registry`.
- [x] `W57-D03` Keep lazy service-loading pattern in extracted modules.

## E) Validation

- [x] `W57-E01` Run focused lint for changed governance modules + boundary test file.
- [x] `W57-E02` Run targeted `skills_*` tests from `test_tools_services.py`.
- [x] `W57-E03` Run `tests/test_import_boundaries.py`.
- [x] `W57-E04` Run full `make check`.
- [x] `W57-E05` Run full `make security-gate`.
- [x] `W57-E06` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W57-F01` Capture post-split line-count outcomes.
- [x] `W57-F02` Commit Wave 57 changes.
- [x] `W57-F03` Push Wave 57 to remote.

---

## Outcome snapshot (completed)

- Governance skills decomposition:
  - `services_domains/governance_skills.py`: `314 -> 19` lines (thin exports).
  - New `services_domains/governance_skills_governance.py`: `217` lines.
  - New `services_domains/governance_skills_registry.py`: `128` lines.
- Boundary enforcement:
  - Added import-boundary coverage for both extracted governance-skills modules.
- Validation status:
  - Focused lint: pass.
  - Targeted `skills_*` tests: pass (`2 passed`, `220 deselected`).
  - `tests/test_import_boundaries.py`: pass (`67 passed`).
  - `make check`: `656 passed`.
  - `make security-gate`: `656 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
