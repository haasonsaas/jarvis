#!/usr/bin/env bash
set -euo pipefail

./scripts/run_soak_profile.py --profile fast --output .artifacts/quality/soak-profile-fast.json
