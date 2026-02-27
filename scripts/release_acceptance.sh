#!/usr/bin/env bash
set -euo pipefail

profile="${1:-full}"

run_core() {
  uv run pytest -q \
    tests/test_brain.py \
    tests/test_presence.py \
    tests/test_voice_attention.py \
    tests/test_turn_taking.py \
    tests/test_tools_services.py -k "system_status or scorecard or identity"
  ./scripts/test_sim_acceptance.sh fast 1
}

run_fast() {
  uv run pytest -q \
    tests/test_brain.py -k "interaction_contract or response_mode or confidence" \
    tests/test_presence.py -k "choreography or muted" \
    tests/test_tools_services.py -k "system_status_contract_reports_expected_fields"
}

uv run ruff check src tests

case "$profile" in
  fast)
    run_fast
    ;;
  full)
    run_core
    ;;
  *)
    echo "Unknown profile: $profile (expected: fast|full)" >&2
    exit 2
    ;;
esac

echo "Release acceptance suite passed ($profile)."
