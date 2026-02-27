# Jarvis TODO — Wave 46 (Trust Memory Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 30
- Completed: 30
- Remaining: 0

---

## A) Scope and baseline

- [x] `W46-A01` Confirm Wave 45 merged and branch baseline clean.
- [x] `W46-A02` Re-profile largest remaining domain modules.
- [x] `W46-A03` Select `services_domains/trust_memory.py` for decomposition.
- [x] `W46-A04` Preserve compatibility import surface.

## B) Decomposition design

- [x] `W46-B01` Define `trust_memory_ops.py` for add/update/forget.
- [x] `W46-B02` Define `trust_memory_query.py` for search/status/recent.
- [x] `W46-B03` Define `trust_memory_summary.py` for summary add/list.
- [x] `W46-B04` Define `trust_memory_governance.py` for quality audit/cleanup controls.
- [x] `W46-B05` Retain lazy `services` lookup and no behavior changes.

## C) Extraction implementation

- [x] `W46-C01` Create `services_domains/trust_memory_ops.py`.
- [x] `W46-C02` Move `memory_add`, `memory_update`, `memory_forget`.
- [x] `W46-C03` Create `services_domains/trust_memory_query.py`.
- [x] `W46-C04` Move `memory_search`, `memory_status`, `memory_recent`.
- [x] `W46-C05` Create `services_domains/trust_memory_summary.py`.
- [x] `W46-C06` Move `memory_summary_add`, `memory_summary_list`.
- [x] `W46-C07` Create `services_domains/trust_memory_governance.py`.
- [x] `W46-C08` Move `_memory_quality_audit` and `memory_governance`.

## D) Compatibility and boundaries

- [x] `W46-D01` Replace `services_domains/trust_memory.py` with compatibility exports.
- [x] `W46-D02` Keep imports expected by `services.py` and `services_server.py` stable.
- [x] `W46-D03` Add import-boundary check for `trust_memory_ops`.
- [x] `W46-D04` Add import-boundary check for `trust_memory_query`.
- [x] `W46-D05` Add import-boundary check for `trust_memory_summary`.
- [x] `W46-D06` Add import-boundary check for `trust_memory_governance`.

## E) Validation

- [x] `W46-E01` Run focused lint on touched trust-memory modules + boundary test.
- [x] `W46-E02` Run targeted pytest for trust-memory handlers + boundaries.
- [x] `W46-E03` Run full `make check`.
- [x] `W46-E04` Run full `make security-gate`.
- [x] `W46-E05` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W46-F01` Capture post-split line-count outcomes.
- [x] `W46-F02` Commit and push Wave 46.

---

## Outcome snapshot (completed)

- Trust-memory decomposition:
  - `services_domains/trust_memory.py`: `600 -> 31` lines (compatibility exports)
  - New `services_domains/trust_memory_ops.py`: `160` lines
  - New `services_domains/trust_memory_query.py`: `243` lines
  - New `services_domains/trust_memory_summary.py`: `70` lines
  - New `services_domains/trust_memory_governance.py`: `160` lines
- Boundary enforcement:
  - Added import-boundary coverage for all new trust-memory modules.
- Validation status:
  - `make check`: `628 passed`
  - `make security-gate`: `628 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
