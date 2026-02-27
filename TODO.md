# Jarvis TODO — Wave 8 (Trust/Proactive Domain Extraction)

Last updated: 2026-02-27

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed

## Completion summary
- Total items: 9
- Completed: 9
- Remaining: 0

---

## A) Service decomposition continuation

- [x] `W8-S01` Extract `proactive_assistant` from `services.py`.
- [x] `W8-S02` Extract `_memory_quality_audit` helper from `services.py`.
- [x] `W8-S03` Extract `memory_governance` from `services.py`.
- [x] `W8-S04` Extract `identity_trust` from `services.py`.
- [x] `W8-S05` Add new domain module `src/jarvis/tools/services_domains/trust.py`.
- [x] `W8-S06` Rewire `services.py` to import trust/proactive handlers from domain module.

## B) Quality and docs

- [x] `W8-Q01` Re-run targeted regression tests for expanded tool surface.
- [x] `W8-Q02` Re-run full quality/security/readiness gates.
- [x] `W8-Q03` Update README tree to reflect trust domain module.

---

## Outcome

- `services.py` reduced from `9,341` lines to `8,890` lines in this wave.
- Strict eval contract remains green at `91/91` cases.
- All local gates pass after extraction.
