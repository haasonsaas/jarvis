#!/usr/bin/env bash
set -euo pipefail

profile="${1:-fast}"

case "$profile" in
  fast|full) ;;
  *)
    echo "Unknown profile: $profile (expected: fast|full)" >&2
    exit 2
    ;;
esac

mkdir -p .artifacts/quality

uv run ruff check src tests
./scripts/check_release_channel.py --channel stable
./scripts/release_acceptance.sh "$profile"
./scripts/run_eval_dataset.py docs/evals/assistant-contract.json \
  --strict \
  --min-pass-rate 1.0 \
  --max-failed 0 \
  --output .artifacts/quality/eval-readiness.json
./scripts/generate_quality_report.py \
  --output-dir .artifacts/quality \
  --markdown \
  > .artifacts/quality/quality-summary.json

echo "Jarvis readiness suite passed (${profile})."
