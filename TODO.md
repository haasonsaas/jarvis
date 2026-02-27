# Jarvis TODO — Wave 5 (Personality + Simulation Validation)

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

## A) Research and design alignment

- [x] `W5-R01` Review assistant personality guidance from major voice UX sources.
- [x] `W5-R02` Capture practical design constraints for safety-sensitive dialog.
- [x] `W5-R03` Define implementation mapping from research to runtime behavior.
- [x] `W5-R04` Publish research notes in docs with source links.

## B) Personality model upgrades

- [x] `W5-P01` Add a first-class `jarvis` persona style to the prompt style model.
- [x] `W5-P02` Support `jarvis` persona normalization in config parsing.
- [x] `W5-P03` Add persona style aliases (`witty`, `classic*`) that normalize to `jarvis`.
- [x] `W5-P04` Add context-aware persona posture classifier (`social|task|safety`).
- [x] `W5-P05` Inject persona posture instruction into per-turn prompt assembly.
- [x] `W5-P06` Ensure high-impact/safety requests route to non-humorous posture.
- [x] `W5-P07` Ensure social/small-talk requests route to light, bounded wit posture.
- [x] `W5-P08` Keep interaction contract and confidence policy integration intact.

## C) Operator/runtime controls

- [x] `W5-O01` Extend valid persona styles in runtime control schema and handlers.
- [x] `W5-O02` Add per-user voice profile `tone` dimension (`auto|formal|witty|empathetic|direct`).
- [x] `W5-O03` Add `tone` parsing in active voice profile resolution.
- [x] `W5-O04` Apply tone-aware guidance in `_with_voice_profile_guidance`.
- [x] `W5-O05` Persist and restore `tone` via runtime state load/save paths.
- [x] `W5-O06` Include `tone` in import/export runtime profile handling.
- [x] `W5-O07` Update operator dashboard buttons for persona `jarvis` and tone presets.
- [x] `W5-O08` Tune demo preset to use `jarvis` persona by default.

## D) Contracts and telemetry

- [x] `W5-C01` Add `tone` default to voice profile snapshots in `system_status`.
- [x] `W5-C02` Extend `system_status_contract` voice profile required fields for `tone`.
- [x] `W5-C03` Keep existing status schema version and compatibility checks green.

## E) Simulation validation and checks

- [x] `W5-S01` Add dedicated simulation regression script (`scripts/test_sim.sh`).
- [x] `W5-S02` Add `make test-sim` target for repeatable sim validation.
- [x] `W5-S03` Include personality/voice-control lifecycle tests in sim suite.
- [x] `W5-S04` Execute sim suite and verify passing results.
- [x] `W5-S05` Re-run full lint/test/security/readiness gates after changes.

## F) Documentation updates

- [x] `W5-D01` Add personality env vars (`PERSONA_STYLE`, `BACKCHANNEL_STYLE`) to `.env.example`.
- [x] `W5-D02` Update README personality section with posture and tone capabilities.
- [x] `W5-D03` Document simulation validation command (`make test-sim`).

---

## Remaining for this wave

All Wave 5 items are implemented and validated in local simulation/testing gates.
