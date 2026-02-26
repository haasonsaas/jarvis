#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools_robot.py tests/test_tools_services.py
