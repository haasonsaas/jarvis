#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q tests/test_main_audio.py -k soak
