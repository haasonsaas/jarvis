# Jarvis TODO — Wave 71 (Status Snapshot Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 35
- Completed: 35
- Remaining: 0

---

## A) Scope and baseline

- [x] `W71-A01` Re-profile post-Wave 70 runtime concentration points.
- [x] `W71-A02` Select `services_status_snapshots_runtime.py` as next hotspot.
- [x] `W71-A03` Preserve exports consumed by `services_status_runtime.py`.
- [x] `W71-A04` Keep status payload compatibility for governance handlers.
- [x] `W71-A05` Keep scorecard/status eval behavior unchanged.

## B) Integration + identity split

- [x] `W71-B01` Create `services_status_integration_identity_runtime.py`.
- [x] `W71-B02` Move `integration_health_snapshot` implementation.
- [x] `W71-B03` Move `identity_status_snapshot` implementation.
- [x] `W71-B04` Preserve guest session pruning semantics.
- [x] `W71-B05` Preserve integration circuit-breaker snapshot payload fields.

## C) Voice + observability split

- [x] `W71-C01` Create `services_status_voice_observability_runtime.py`.
- [x] `W71-C02` Move `voice_attention_snapshot` implementation.
- [x] `W71-C03` Move `observability_snapshot` implementation.
- [x] `W71-C04` Move `skills_status_snapshot` implementation.
- [x] `W71-C05` Preserve default payload fill-in behavior for missing state dictionaries.

## D) Expansion + health split

- [x] `W71-D01` Create `services_status_expansion_health_runtime.py`.
- [x] `W71-D02` Move `expansion_snapshot` implementation.
- [x] `W71-D03` Move `health_rollup` implementation.
- [x] `W71-D04` Preserve expansion counters and release-channel diagnostics.
- [x] `W71-D05` Preserve health-degraded/error reason behavior.

## E) Wrapper + boundaries

- [x] `W71-E01` Reduce `services_status_snapshots_runtime.py` to compatibility wrapper.
- [x] `W71-E02` Add import-boundary coverage for `services_status_integration_identity_runtime`.
- [x] `W71-E03` Add import-boundary coverage for `services_status_voice_observability_runtime`.
- [x] `W71-E04` Add import-boundary coverage for `services_status_expansion_health_runtime`.
- [x] `W71-E05` Run focused lint on changed status runtime files.

## F) Validation + release

- [x] `W71-F01` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W71-F02` Run targeted status/scorecard tool tests.
- [x] `W71-F03` Run full `make check`.
- [x] `W71-F04` Run full `make security-gate`.
- [x] `W71-F05` Run `./scripts/jarvis_readiness.sh fast`.
- [x] `W71-F06` Record line-count deltas and extracted module list.
- [x] `W71-F07` Commit Wave 71 tranche.
- [x] `W71-F08` Push Wave 71 to `origin/main`.

---

## Outcome snapshot (completed)

- Wrapper concentration reduction:
  - `services_status_snapshots_runtime.py`: `449 -> 27`
- New extracted modules:
  - `services_status_integration_identity_runtime.py`
  - `services_status_voice_observability_runtime.py`
  - `services_status_expansion_health_runtime.py`
- Validation status:
  - `uv run pytest -q tests/test_import_boundaries.py`: `156 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "system_status or jarvis_scorecard or status_contract or observability or voice"`: `7 passed`.
  - `make check`: `745 passed`.
  - `make security-gate`: `745 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
