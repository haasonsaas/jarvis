# Jarvis TODO — Wave 39 (Domain Decomposition: Trust + Governance)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 28
- Completed: 28
- Remaining: 0

---

## A) Scope and baseline

- [x] `W39-A01` Confirm post-W38 baseline and identify largest remaining domain files.
- [x] `W39-A02` Define refactor objective: split trust domain by responsibility.
- [x] `W39-A03` Define refactor objective: split governance status/contract builders.

## B) Trust domain decomposition

- [x] `W39-B01` Extract all memory handlers into `services_domains/trust_memory.py`.
- [x] `W39-B02` Extract memory-governance helper logic into `trust_memory.py`.
- [x] `W39-B03` Extract identity trust handlers into `services_domains/trust_identity.py`.
- [x] `W39-B04` Reduce `services_domains/trust.py` to proactive-only handlers.
- [x] `W39-B05` Preserve `_services()` lazy module resolution pattern in all new modules.

## C) Service wiring updates

- [x] `W39-C01` Update `services.py` compatibility exports to import memory handlers from `trust_memory.py`.
- [x] `W39-C02` Update `services.py` compatibility exports to import identity handlers from `trust_identity.py`.
- [x] `W39-C03` Keep `proactive_assistant` export sourced from `trust.py`.
- [x] `W39-C04` Update MCP server registration imports in `services_server.py` for new modules.

## D) Governance decomposition

- [x] `W39-D01` Add `services_governance_runtime.py` for shared status runtime helpers.
- [x] `W39-D02` Move tool-policy status snapshot builder into runtime helper module.
- [x] `W39-D03` Move scorecard-context construction into runtime helper module.
- [x] `W39-D04` Move system-status payload construction into runtime helper module.
- [x] `W39-D05` Move full system-status contract payload template into runtime helper module.
- [x] `W39-D06` Rewire governance domain handlers to call runtime helper functions.

## E) Boundary and safety checks

- [x] `W39-E01` Extend import boundary tests for `trust_memory` module.
- [x] `W39-E02` Extend import boundary tests for `trust_identity` module.
- [x] `W39-E03` Extend import boundary tests for `services_governance_runtime` module.
- [x] `W39-E04` Keep service API surface unchanged for existing tests/callers.

## F) Validation

- [x] `W39-F01` Run focused lint for changed files.
- [x] `W39-F02` Run targeted pytest for trust/governance/system-status behavior.
- [x] `W39-F03` Run `make check` full suite.
- [x] `W39-F04` Run `make security-gate`.
- [x] `W39-F05` Run `./scripts/jarvis_readiness.sh fast`.

## G) Release loop

- [x] `W39-G01` Update TODO completion snapshot with decomposition outcomes.
- [x] `W39-G02` Commit and push Wave 39 refactor set.

---

## Outcome snapshot (completed)

- Domain decomposition completed:
  - `services_domains/trust.py`: `1173 -> 419` lines (proactive only)
  - New `services_domains/trust_memory.py`: memory + governance handlers
  - New `services_domains/trust_identity.py`: identity trust handlers
- Governance decomposition completed:
  - `services_domains/governance.py`: `1131 -> 649` lines
  - New `services_governance_runtime.py`: status/contract context and payload builders
- Wiring preserved:
  - Compatibility exports in `services.py` unchanged at call surface.
  - MCP tool registration in `services_server.py` updated to new domain modules.
- Validation status:
  - `make check`: `603 passed`
  - `make security-gate`: `603 passed`; fault subset `3 passed`
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`
