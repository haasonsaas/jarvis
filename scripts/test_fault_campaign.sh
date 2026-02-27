#!/usr/bin/env bash
set -euo pipefail

profiles="${1:-quick,network,storage,contract}"
repeat="${2:-2}"

if ! [[ "${repeat}" =~ ^[0-9]+$ ]]; then
  echo "repeat must be a positive integer" >&2
  exit 2
fi
if [[ "${repeat}" -lt 1 ]]; then
  echo "repeat must be >= 1" >&2
  exit 2
fi

./scripts/run_fault_campaign.py \
  --profiles "${profiles}" \
  --repeat "${repeat}"
