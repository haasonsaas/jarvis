# Skills Development Guide

## Overview

Jarvis discovers local skills from `SKILLS_DIR`.
Each skill is a folder containing `skill.json`.

- Discovery: on startup and via operator action `skills_reload`
- Lifecycle: `skills_list`, `skills_enable`, `skills_disable`, `skills_version`
- Status: surfaced under `system_status.skills`

## Manifest Contract

Path:
- `<SKILLS_DIR>/<skill_name>/skill.json`

Minimal example:

```json
{
  "name": "weather_plus",
  "version": "1.0.0",
  "namespace": "skill.weather_plus",
  "description": "Weather-focused helper skill",
  "capabilities": ["forecast", "alerts"],
  "allowed_network_domains": ["api.weather.example"],
  "allowed_paths": ["/tmp"],
  "signature": "<optional-hex-hmac-sha256>"
}
```

## Namespace Convention

- Required prefix: `skill.`
- Owner segment must match `name`
- Example: `name=planner` => `namespace=skill.planner`

## Signature Policy

When `SKILLS_REQUIRE_SIGNATURE=true`, unsigned/invalid skills are blocked.

Signature input string:
- `name|version|namespace|capability1,capability2,...`

Signature algorithm:
- HMAC-SHA256 with `SKILLS_SIGNATURE_KEY`
- store hex digest in `signature`

## Allowlist Policy

- `SKILLS_ALLOWLIST` is a comma-separated list of skill names.
- If non-empty, non-allowlisted skills are blocked at load time.

## Failure Modes

- Invalid JSON/shape: `status=error`, `load_error=invalid_manifest:*`
- Invalid naming/namespace: `status=error`
- Policy block (allowlist/signature): `status=blocked`
- Runtime remains healthy even if some skills fail to load.

## Validation Checklist

1. `make check`
2. Confirm skill appears in `skills_list`
3. Confirm `system_status.skills.skills[*].status == "loaded"`
4. Disable and re-enable skill with lifecycle tools
