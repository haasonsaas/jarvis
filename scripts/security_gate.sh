#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

required_docs=(
  "docs/operations/release-checklist.md"
  "docs/operations/security-maintenance.md"
  "docs/operations/provenance-verification.md"
  "docs/operations/incident-response.md"
)

for path in "${required_docs[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required security doc: $path" >&2
    exit 1
  fi
done

echo "[security-gate] Running lint + full tests"
./scripts/check.sh

echo "[security-gate] Running fault-injection subset"
./scripts/test_faults.sh

echo "[security-gate] Verifying workflow action pins"
python - <<'PY'
from __future__ import annotations

import pathlib
import re
import sys

workflow_root = pathlib.Path('.github/workflows')
uses_re = re.compile(r"^\s*uses:\s*([^\s]+)")
sha_re = re.compile(r"^[0-9a-f]{40}$")

violations: list[str] = []
for path in sorted(workflow_root.glob('*.yml')):
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        m = uses_re.match(line)
        if not m:
            continue
        ref = m.group(1)
        if ref.startswith('./'):
            continue
        if '@' not in ref:
            violations.append(f"{path}:{idx}: missing @ref pin")
            continue
        _, version = ref.split('@', 1)
        if not sha_re.match(version):
            violations.append(f"{path}:{idx}: not pinned to full commit SHA ({ref})")

if violations:
    print("Action pin violations:")
    for item in violations:
        print(f"- {item}")
    sys.exit(1)
PY

echo "[security-gate] OK"
