# Home Assistant Add-on Path

This directory contains a starter add-on packaging profile for running Jarvis on a Home Assistant host.

## Build/packaging notes

- `config.yaml`: add-on metadata and options schema.
- `Dockerfile`: base image plus Jarvis runtime dependencies.
- The runtime command starts Jarvis in simulation/no-vision mode by default for safer first boot.

## Installation workflow

1. Copy this folder into a Home Assistant add-on repository.
2. Provide API keys in add-on options or environment overrides.
3. Build and install via Home Assistant Supervisor.
4. Validate with dry-run tooling before enabling mutating integrations.
