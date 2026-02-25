#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools.py
