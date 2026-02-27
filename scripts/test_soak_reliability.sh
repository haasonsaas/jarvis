#!/usr/bin/env bash
set -euo pipefail

repeat="${1:-3}"
if ! [[ "${repeat}" =~ ^[0-9]+$ ]]; then
  echo "repeat must be a positive integer" >&2
  exit 2
fi
if [[ "${repeat}" -lt 1 ]]; then
  echo "repeat must be >= 1" >&2
  exit 2
fi

./scripts/run_soak_profile.py \
  --profile fast \
  --repeat "${repeat}" \
  --output ".artifacts/quality/soak-profile-fast-repeat${repeat}.json"
