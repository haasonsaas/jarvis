# Jarvis TODO — Wave 65 (Smart-Home Mutation Policy Split)

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

- [x] `W65-A01` Profile post-Wave-64 hotspots and select highest policy-concentration candidate.
- [x] `W65-A02` Select `home_mutation_policy.py` for focused decomposition.
- [x] `W65-A03` Preserve all `smart_home` response text and policy decisions.
- [x] `W65-A04` Preserve identity/audit/preview semantics and guardrail ordering.

## B) Validation + identity split

- [x] `W65-B01` Create `home_mutation_policy_validate_identity.py`.
- [x] `W65-B02` Move field/domain/action/data validation checks.
- [x] `W65-B03` Move dry-run/safe-mode normalization.
- [x] `W65-B04` Move identity authorization and denied audit path.
- [x] `W65-B05` Move strict-confirm and sensitive-confirm enforcement.
- [x] `W65-B06` Return normalized context payload for downstream guardrails.

## C) Guardrail split

- [x] `W65-C01` Create `home_mutation_policy_guardrails.py`.
- [x] `W65-C02` Move ambiguous high-risk target denial logic.
- [x] `W65-C03` Move area-policy enforcement logic.
- [x] `W65-C04` Move plan-preview gating and preview audit path.
- [x] `W65-C05` Preserve preview risk-level mapping by domain sensitivity.

## D) Wrapper reduction

- [x] `W65-D01` Reduce `home_mutation_policy.py` to orchestrator wrapper.
- [x] `W65-D02` Wire wrapper through validate-then-guardrails flow.

## E) Boundaries and validation

- [x] `W65-E01` Extend import-boundary coverage for new policy split modules.
- [x] `W65-E02` Run focused lint on changed modules.
- [x] `W65-E03` Run targeted pytest for `smart_home` behavior.
- [x] `W65-E04` Run `tests/test_import_boundaries.py`.
- [x] `W65-E05` Run full `make check`.
- [x] `W65-E06` Run full `make security-gate`.
- [x] `W65-E07` Run `./scripts/jarvis_readiness.sh fast`.

## F) Release loop

- [x] `W65-F01` Record line-count outcomes for split module.
- [x] `W65-F02` Commit Wave 65 tranche.
- [x] `W65-F03` Push Wave 65 to origin/main.

---

## Outcome snapshot (completed)

- Wrapper concentration reduction:
  - `home_mutation_policy.py`: `231 -> 26`
- New extracted modules:
  - `home_mutation_policy_validate_identity.py`
  - `home_mutation_policy_guardrails.py`
- Validation status:
  - Focused lint: pass.
  - Targeted pytest (`smart_home`): `41 passed`.
  - `tests/test_import_boundaries.py`: pass.
  - `make check`: `702 passed`.
  - `make security-gate`: `702 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
