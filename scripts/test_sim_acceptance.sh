#!/usr/bin/env bash
set -euo pipefail

profile="${1:-fast}"
repeat="${2:-1}"

if ! [[ "${repeat}" =~ ^[0-9]+$ ]]; then
  echo "repeat must be a positive integer" >&2
  exit 2
fi
if [[ "${repeat}" -lt 1 ]]; then
  echo "repeat must be >= 1" >&2
  exit 2
fi

./scripts/run_sim_acceptance.py \
  --profile "${profile}" \
  --repeat "${repeat}" \
  --output ".artifacts/quality/sim-acceptance-${profile}-repeat${repeat}.json"
