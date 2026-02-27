# Jarvis TODO — Wave 69 (Runtime State + Audit Runtime Decomposition)

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

- [x] `W69-A01` Profile remaining large runtime modules after Wave 68.
- [x] `W69-A02` Select `services_runtime_state.py` for decomposition.
- [x] `W69-A03` Select `services_audit_runtime.py` for decomposition.
- [x] `W69-A04` Preserve `services.py` import contracts and helper names.
- [x] `W69-A05` Keep behavior parity for bind/bootstrap, persistence, and audit flows.

## B) Runtime state split

- [x] `W69-B01` Create `services_runtime_state_bind.py`.
- [x] `W69-B02` Move `bind_runtime_state` implementation.
- [x] `W69-B03` Move `_reset_runtime_state` implementation into bind module scope.
- [x] `W69-B04` Create `services_runtime_state_reports.py`.
- [x] `W69-B05` Move `quality_reports_snapshot` implementation.
- [x] `W69-B06` Move `append_quality_report` implementation.
- [x] `W69-B07` Create `services_runtime_state_persistence.py`.
- [x] `W69-B08` Move `json_safe_clone`/`replace_state_dict` helpers.
- [x] `W69-B09` Move expansion payload/persist/load helpers.
- [x] `W69-B10` Reduce `services_runtime_state.py` to compatibility wrapper.

## C) Audit runtime split

- [x] `W69-C01` Create `services_audit_crypto_runtime.py`.
- [x] `W69-C02` Move audit encryption/decryption helpers.
- [x] `W69-C03` Create `services_audit_event_runtime.py`.
- [x] `W69-C04` Move audit outcome/reason/humanization helpers.
- [x] `W69-C05` Move decision explanation + audit write/rotate helpers.
- [x] `W69-C06` Create `services_audit_sanitize_runtime.py`.
- [x] `W69-C07` Move redaction + metadata-only + inbound sanitizer helpers.
- [x] `W69-C08` Create `services_audit_retention_runtime.py`.
- [x] `W69-C09` Move audit status/prune/retention helpers.
- [x] `W69-C10` Reduce `services_audit_runtime.py` to compatibility wrapper.

## D) Boundary and quality verification

- [x] `W69-D01` Extend import-boundary coverage for runtime-state split modules.
- [x] `W69-D02` Extend import-boundary coverage for audit split modules.
- [x] `W69-D03` Run focused lint on all changed runtime modules.
- [x] `W69-D04` Run `uv run pytest -q tests/test_import_boundaries.py`.
- [x] `W69-D05` Run targeted tools tests for audit + expansion/state status paths.
- [x] `W69-D06` Run full `make check`.
- [x] `W69-D07` Run full `make security-gate`.
- [x] `W69-D08` Run `./scripts/jarvis_readiness.sh fast`.

## E) Release loop

- [x] `W69-E01` Record wrapper reduction deltas and new module inventory.
- [x] `W69-E02` Commit Wave 69 tranche.
- [x] `W69-E03` Push Wave 69 tranche to `origin/main`.

---

## Outcome snapshot (completed)

- Wrapper concentration reductions:
  - `services_runtime_state.py`: `491 -> 27`
  - `services_audit_runtime.py`: `416 -> 49`
- New extracted modules:
  - `services_runtime_state_bind.py`
  - `services_runtime_state_reports.py`
  - `services_runtime_state_persistence.py`
  - `services_audit_crypto_runtime.py`
  - `services_audit_event_runtime.py`
  - `services_audit_sanitize_runtime.py`
  - `services_audit_retention_runtime.py`
- Validation status:
  - `uv run pytest -q tests/test_import_boundaries.py`: `144 passed`.
  - `uv run pytest -q tests/test_tools_services.py -k "audit_log or prune_audit_file or inbound_webhook_event or expansion_state_persists_across_bind or integration_hub_release_channel_actions or system_status"`: `18 passed`.
  - `make check`: `733 passed`.
  - `make security-gate`: `733 passed`; fault subset `3 passed`.
  - `./scripts/jarvis_readiness.sh fast`: pass; strict eval `159/159`.
