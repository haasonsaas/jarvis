#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _run_check(base: Path, check: dict[str, Any]) -> dict[str, Any]:
    kind = str(check.get("type", "")).strip().lower()
    path = str(check.get("path", "")).strip()
    target = (base / path).resolve() if path else base

    if kind == "file_exists":
        ok = target.exists()
        return {"type": kind, "path": path, "ok": ok, "detail": "exists" if ok else "missing"}

    if kind == "text_contains":
        needle = str(check.get("needle", "")).strip()
        if not target.exists() or not target.is_file():
            return {"type": kind, "path": path, "ok": False, "detail": "missing_file"}
        text = target.read_text(encoding="utf-8", errors="replace")
        ok = needle in text
        return {
            "type": kind,
            "path": path,
            "needle": needle,
            "ok": ok,
            "detail": "found" if ok else "missing_needle",
        }

    return {"type": kind or "unknown", "path": path, "ok": False, "detail": "unsupported_check_type"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate staged release-channel checks.")
    parser.add_argument("--channel", required=True, choices=["dev", "beta", "stable"])
    parser.add_argument("--config", default="config/release-channels.json")
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    config_path = (workspace / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    channels = config.get("channels", {}) if isinstance(config, dict) else {}
    channel_cfg = channels.get(args.channel, {}) if isinstance(channels, dict) else {}
    checks = channel_cfg.get("required_checks", []) if isinstance(channel_cfg, dict) else []

    results = [_run_check(workspace, row) for row in checks if isinstance(row, dict)]
    failed = [row for row in results if not bool(row.get("ok"))]

    payload = {
        "channel": args.channel,
        "passed": len(failed) == 0,
        "check_count": len(results),
        "failed_count": len(failed),
        "results": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
