#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_DAEMON=0
REINSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --daemon)
      RUN_DAEMON=1
      ;;
    --reinstall)
      REINSTALL=1
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--daemon] [--reinstall]" >&2
      exit 1
      ;;
  esac
  shift
done

mkdir -p .artifacts/reachy-app-smoke

echo "[1/4] Reachy Mini app structure check"
./.venv/bin/reachy-mini-app-assistant check .

echo "[2/4] Verify app entrypoint"
./.venv/bin/python - <<'PY'
from importlib.metadata import entry_points

eps = entry_points(group="reachy_mini_apps")
names = sorted(ep.name for ep in eps)
assert "jarvis" in names, f"jarvis missing from entry points: {names}"
print("Registered app entry points:", ", ".join(names))
PY

if [[ "$REINSTALL" == "1" ]]; then
  echo "[3/4] Reinstall editable package"
  ./.venv/bin/python -m pip install -e .
else
  echo "[3/4] Skipping editable reinstall (pass --reinstall to force it)"
fi

if [[ "$RUN_DAEMON" == "1" ]]; then
  echo "[4/4] Start reachy-mini-daemon for dashboard smoke path"
  if ! command -v reachy-mini-daemon >/dev/null 2>&1; then
    echo "reachy-mini-daemon is not installed or not on PATH." >&2
    exit 1
  fi

  DAEMON_LOG=".artifacts/reachy-app-smoke/daemon.log"
  : > "$DAEMON_LOG"
  reachy-mini-daemon >"$DAEMON_LOG" 2>&1 &
  DAEMON_PID=$!
  trap 'kill "$DAEMON_PID" >/dev/null 2>&1 || true' EXIT

  READY=0
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:8000/ >/dev/null 2>&1; then
      READY=1
      break
    fi
    sleep 1
  done

  if [[ "$READY" != "1" ]]; then
    echo "reachy-mini-daemon did not become ready at http://127.0.0.1:8000/" >&2
    echo "See $DAEMON_LOG" >&2
    exit 1
  fi

  echo "Daemon is reachable. Complete the remaining manual checks in docs/operations/reachy-app-smoke-test.md:"
  echo "- install the HF app from the dashboard"
  echo "- run/stop it"
  echo "- open the settings UI"
  echo "- verify motion/audio behavior on target hardware"
else
  echo "[4/4] Daemon smoke path not run (pass --daemon to enable)"
fi
