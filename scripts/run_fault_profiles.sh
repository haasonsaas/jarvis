#!/usr/bin/env bash
set -euo pipefail

profile="${1:-quick}"

case "$profile" in
  quick)
    pattern="timeout or cancelled or invalid_json or api_error or storage_error or missing_store or unknown_error or summary_unavailable or http_error or network_client_error"
    ;;
  network)
    pattern="failed and reach and parameterized"
    ;;
  storage)
    pattern="timed and parameterized"
    ;;
  contract)
    pattern="cancelled and parameterized"
    ;;
  all)
    for name in quick network storage contract; do
      "$0" "$name"
    done
    exit 0
    ;;
  *)
    echo "Unknown fault profile: $profile" >&2
    echo "Expected one of: quick, network, storage, contract, all" >&2
    exit 2
    ;;
esac

uv run pytest -q tests/test_tools_services.py -m fault -k "$pattern"
