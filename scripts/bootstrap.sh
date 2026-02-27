#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/bootstrap.sh [--quick]

Bootstraps Jarvis on a clean host:
- ensures uv is installed
- syncs dependencies
- creates .env from .env.example if missing
- runs baseline validation (unless --quick)
USAGE
}

quick=false
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--quick" ]]; then
  quick=true
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

uv sync --extra dev

if [[ "$quick" == "false" ]]; then
  uv run ruff check src tests
  uv run pytest -q tests/test_config.py tests/test_tools_services.py
fi

echo "Bootstrap complete."
