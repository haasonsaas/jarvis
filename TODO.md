# Jarvis TODO — Wave 16 (Services Integration Runtime Decomposition)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 4
- Completed: 4
- Remaining: 0

---

## A) Decomposition

- [x] `W16-S01` Extract release-channel helper stack (`_run_release_channel_check`, `_load_release_channel_config`, `_evaluate_release_channel`) into `src/jarvis/tools/services_integrations_runtime.py`.
- [x] `W16-S02` Extract notes/report artifact helpers (`_write_quality_report_artifact`, `_capture_note`, `_notion_configured`, `_capture_note_notion`) into `services_integrations_runtime.py`.
- [x] `W16-S03` Keep compatibility wrappers in `src/jarvis/tools/services.py` so existing domain modules and imports keep the same callable names.

## B) Quality and verification

- [x] `W16-Q01` Re-run full `make check`, `make security-gate`, and readiness full suite after extraction.

---

## Outcome snapshot (current)

- New integration runtime helper module: `src/jarvis/tools/services_integrations_runtime.py`.
- `src/jarvis/tools/services.py` reduced to `3,571` lines (from `3,730` before this wave).
- Full gates are green:
  - `make check` (`555 passed`)
  - `make security-gate` (`555 passed`; fault-injection subset `3 passed`)
  - `./scripts/jarvis_readiness.sh full` (`91/91` strict eval)
