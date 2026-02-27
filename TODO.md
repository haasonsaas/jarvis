# Jarvis TODO — Wave 45 (Governance Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 31
- Completed: 31
- Remaining: 0

---

## A) Scope and baseline

- [x] `W45-A01` Confirm Wave 44 merged and tree clean before new edits.
- [x] `W45-A02` Re-profile largest remaining service-domain modules.
- [x] `W45-A03` Select `services_domains/governance.py` for decomposition.
- [x] `W45-A04` Preserve external API via compatibility exports.

## B) Decomposition design

- [x] `W45-B01` Define `governance_tool_summary.py` for summary endpoints.
- [x] `W45-B02` Define `governance_skills.py` for skills governance and lifecycle ops.
- [x] `W45-B03` Define `governance_quality.py` for quality and embodiment handlers.
- [x] `W45-B04` Define `governance_status.py` for system status contract/scorecard.
- [x] `W45-B05` Keep lazy `services` lookup pattern unchanged in all new modules.

## C) Extraction implementation

- [x] `W45-C01` Create `services_domains/governance_tool_summary.py`.
- [x] `W45-C02` Move `tool_summary` and `tool_summary_text`.
- [x] `W45-C03` Create `services_domains/governance_skills.py`.
- [x] `W45-C04` Move `_skills_snapshot_rows` and `skills_governance`.
- [x] `W45-C05` Move `skills_list`, `skills_enable`, `skills_disable`, `skills_version`.
- [x] `W45-C06` Create `services_domains/governance_quality.py`.
- [x] `W45-C07` Move `quality_evaluator` and `embodiment_presence`.
- [x] `W45-C08` Create `services_domains/governance_status.py`.
- [x] `W45-C09` Move `system_status`, `system_status_contract`, and `jarvis_scorecard`.

## D) Compatibility and boundaries

- [x] `W45-D01` Replace `services_domains/governance.py` with compatibility exports.
- [x] `W45-D02` Preserve imports expected by `services.py` and `services_server.py`.
- [x] `W45-D03` Add import-boundary check for `governance_tool_summary`.
- [x] `W45-D04` Add import-boundary check for `governance_skills`.
- [x] `W45-D05` Add import-boundary check for `governance_quality`.
- [x] `W45-D06` Add import-boundary check for `governance_status`.

## E) Validation

- [x] `W45-E01` Run focused lint on changed governance modules + boundary tests.
- [x] `W45-E02` Run targeted pytest for governance handlers + import boundaries.
- [x] `W45-E03` Run full `make check`.
- [x] `W45-E04` Run full `make security-gate`.
- [x] `W45-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W45-F01` Capture post-split governance line-count results.
- [x] `W45-F02` Commit and push Wave 45.

---

## Outcome snapshot (completed)

- Governance decomposition:
  - `services_domains/governance.py`: `649 -> 39` lines (compatibility exports)
  - New `services_domains/governance_tool_summary.py`: `59` lines
  - New `services_domains/governance_skills.py`: `314` lines
  - New `services_domains/governance_quality.py`: `201` lines
  - New `services_domains/governance_status.py`: `105` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new governance modules.
- Validation status:
  - `make check`: `624 passed`
  - `make security-gate`: `624 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
