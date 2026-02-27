# Jarvis TODO — Wave 21 (Audit and Redaction Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 6
- Completed: 6
- Remaining: 0

---

## A) Decomposition

- [x] `W21-S01` Extract audit encryption/decryption helpers from `services.py` into `src/jarvis/tools/services_audit_runtime.py` (`_configure_audit_encryption`, `_encrypt_audit_line`, `_decode_audit_line`).
- [x] `W21-S02` Extract audit decision narrative helpers (`_audit_outcome`, `_audit_reason_code`, `_humanize_chain_token`, `_audit_decision_explanation`) into `services_audit_runtime.py`.
- [x] `W21-S03` Extract audit logging and redaction helpers (`_audit`, `_rotate_audit_log_if_needed`, `_redact_sensitive_for_audit`, `_metadata_only_audit_details`) into `services_audit_runtime.py`.
- [x] `W21-S04` Extract inbound sanitization and PII helpers (`_sanitize_inbound_headers`, `_sanitize_inbound_payload`, `_contains_pii`) into `services_audit_runtime.py`.
- [x] `W21-S05` Replace extracted functions in `services.py` with compatibility wrappers, keeping runtime constants exported via `services` module alias.

## B) Quality and verification

- [x] `W21-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New audit runtime helper module: `src/jarvis/tools/services_audit_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `2,361` lines (from `2,576` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
