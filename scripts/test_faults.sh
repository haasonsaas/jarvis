#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q tests/test_tools_services.py -m fault -k "timeout or cancelled or invalid_json or api_error or storage_error or missing_store or unknown_error or summary_unavailable or http_error or network_client_error"
