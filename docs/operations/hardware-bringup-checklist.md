# Hardware Bring-Up Checklist

## Purpose

Use this checklist when first hardware arrives to reduce bring-up risk and keep behavior aligned with simulation.

## 1) Host and Environment Preflight

- Verify Python and dependency sync:
  - `uv sync --extra dev`
- Verify baseline quality gates:
  - `make check`
  - `make security-gate`
- Verify simulation acceptance before touching hardware:
  - `make test-sim-acceptance`

## 2) Reachy Connectivity and Safety

- Confirm robot connectivity mode and host values in config/env.
- Start in conservative mode:
  - motion disabled for first boot validation (`--no-motion`)
  - home actions disabled for first boot validation (`--no-home`)
- Verify emergency stop procedure and physical clear zone before enabling motion.

## 3) Audio Bring-Up

- Validate input/output devices and sample-rate assumptions.
- Run with TTS disabled first:
  - `uv run python -m jarvis --sim --no-tts --debug`
- Enable TTS only after stable STT turn capture.

## 4) Vision and Hands Bring-Up

- Validate camera stream availability and frame latency.
- Enable vision path first, then hand tracking:
  - `uv run python -m jarvis --debug --no-hands`
  - `uv run python -m jarvis --debug`
- Confirm no presence-loop deadlocks or tracker crashes.

## 5) Operator and Trust Controls

- Validate operator status endpoints and auth mode posture.
- Keep strict confirmation enabled during early live runs.
- Verify identity guardrails with non-destructive tool calls first.

## 6) Smart Home and Integration Bring-Up

- Keep mutating integrations in dry-run until trust checks pass.
- Verify Home Assistant read-only actions before mutating actions.
- Verify webhook allowlist and TLS constraints before enabling outbound triggers.

## 7) Final Acceptance on Hardware

- Re-run readiness and campaign gates after hardware config is enabled:
  - `./scripts/jarvis_readiness.sh fast`
  - `make quality-trend-gate`
- Capture artifacts and startup diagnostics for first successful live baseline.
