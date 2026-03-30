# Changelog

All notable user-facing changes to the published Reachy Mini app should be recorded here.

## [0.1.1] - 2026-03-30

### Added
- Reachy Mini app compatibility checks in CI.
- Reachy app smoke-test script and hardware runbook.
- Bundled app readiness diagnostics in the settings UI.
- Published Space preview asset for the Hugging Face landing page.

### Changed
- Reduced default install weight by making local workstation audio optional.
- Replaced the hard `scipy` resampling dependency with an in-repo fallback.
- Face-tracker startup now degrades gracefully and reports warnings instead of aborting the full runtime.

## [0.1.0] - 2026-03-30

### Added
- `ReachyMiniApp` entrypoint and packaged settings UI.
- Hugging Face Space metadata and landing assets.
- Reachy Mini app packaging tests and publish flow.
