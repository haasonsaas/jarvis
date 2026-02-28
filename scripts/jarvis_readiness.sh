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
  --min-cases 250 \
  --require-unique-ids \
  --require-expected-tools \
  --output .artifacts/quality/eval-readiness.json
./scripts/run_router_policy_eval.py docs/evals/router-policy-contract.json \
  --strict \
  --min-pass-rate 1.0 \
  --max-failed 0 \
  --min-cases 20 \
  --require-unique-ids \
  --output .artifacts/quality/router-policy-eval-readiness.json
./scripts/run_interruption_route_eval.py docs/evals/interruption-route-contract.json \
  --strict \
  --min-pass-rate 1.0 \
  --max-failed 0 \
  --min-cases 20 \
  --require-unique-ids \
  --output .artifacts/quality/interruption-route-eval-readiness.json
./scripts/run_trace_trajectory_eval.py docs/evals/trajectory-trace-contract.json \
  --strict \
  --min-pass-rate 1.0 \
  --max-failed 0 \
  --min-cases 10 \
  --require-unique-ids \
  --output .artifacts/quality/trajectory-trace-eval-readiness.json
./scripts/run_autonomy_cycle_eval.py docs/evals/autonomy-cycle-contract.json \
  --strict \
  --min-pass-rate 1.0 \
  --max-failed 0 \
  --min-cases 10 \
  --require-unique-ids \
  --output .artifacts/quality/autonomy-cycle-eval-readiness.json
uv run python scripts/run_runtime_outcome_gate.py \
  --strict \
  --min-pass-rate 1.0 \
  --max-failed 0 \
  --output .artifacts/quality/runtime-outcome-gate-readiness.json
./scripts/generate_quality_report.py \
  --output-dir .artifacts/quality \
  --markdown \
  > .artifacts/quality/quality-summary.json

if [[ "$profile" == "full" ]]; then
  ./scripts/check_quality_trends.py \
    --soak-artifact .artifacts/quality/soak-profile-fast.json \
    --fault-artifact .artifacts/quality/fault-campaign-quick-repeat1.json \
    --baseline config/quality-trend-baselines.json \
    --output .artifacts/quality/quality-trend-gate.json
fi

echo "Jarvis readiness suite passed (${profile})."
