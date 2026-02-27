#!/usr/bin/env bash
set -euo pipefail

profile="${1:-full}"
./scripts/run_soak_profile.py --profile "${profile}" --output .artifacts/quality/soak-profile.json
