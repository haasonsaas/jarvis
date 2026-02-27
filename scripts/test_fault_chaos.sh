#!/usr/bin/env bash
set -euo pipefail

profiles="${1:-quick,network,storage,contract}"
permutations="${2:-2}"

if ! [[ "${permutations}" =~ ^[0-9]+$ ]]; then
  echo "permutations must be a positive integer" >&2
  exit 2
fi
if [[ "${permutations}" -lt 1 ]]; then
  echo "permutations must be >= 1" >&2
  exit 2
fi

./scripts/run_fault_chaos.py \
  --profiles "${profiles}" \
  --permutations "${permutations}"
