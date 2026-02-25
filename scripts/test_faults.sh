#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q tests/test_tools.py -k "timeout or cancelled or invalid_json or storage_error or unavailable"
