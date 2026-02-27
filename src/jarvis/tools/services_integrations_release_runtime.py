"""Release-channel and report-artifact helpers for services domains."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

def run_release_channel_check(base: Path, check: dict[str, Any]) -> dict[str, Any]:
    kind = str(check.get("type", "")).strip().lower()
    path = str(check.get("path", "")).strip()
    target = (base / path).resolve() if path else base

    if kind == "file_exists":
        ok = target.exists()
        return {"type": kind, "path": path, "ok": ok, "detail": "exists" if ok else "missing"}

    if kind == "text_contains":
        needle = str(check.get("needle", "")).strip()
        if not target.exists() or not target.is_file():
            return {"type": kind, "path": path, "needle": needle, "ok": False, "detail": "missing_file"}
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"type": kind, "path": path, "needle": needle, "ok": False, "detail": "read_failed"}
        ok = needle in text
        return {
            "type": kind,
            "path": path,
            "needle": needle,
            "ok": ok,
            "detail": "found" if ok else "missing_needle",
        }

    return {"type": kind or "unknown", "path": path, "ok": False, "detail": "unsupported_check_type"}


def load_release_channel_config(services_module: Any) -> tuple[dict[str, Any] | None, str]:
    path = services_module._release_channel_config_path
    if not path.exists():
        return None, f"release channel config missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, f"release channel config unreadable: {path}"
    if not isinstance(payload, dict):
        return None, f"release channel config invalid format: {path}"
    return payload, ""


def evaluate_release_channel(
    services_module: Any,
    *,
    channel: str,
    workspace: Path | None = None,
) -> dict[str, Any]:
    normalized_channel = str(channel or "").strip().lower()
    if normalized_channel not in services_module.RELEASE_CHANNELS:
        return {
            "channel": normalized_channel,
            "passed": False,
            "check_count": 0,
            "failed_count": 1,
            "results": [],
            "migration_checks": [],
            "error": f"Unsupported release channel: {normalized_channel or '<empty>'}.",
        }

    config_payload, error = load_release_channel_config(services_module)
    if config_payload is None:
        return {
            "channel": normalized_channel,
            "passed": False,
            "check_count": 0,
            "failed_count": 1,
            "results": [],
            "migration_checks": [],
            "error": error,
        }

    channels = config_payload.get("channels", {}) if isinstance(config_payload, dict) else {}
    channel_cfg = channels.get(normalized_channel, {}) if isinstance(channels, dict) else {}
    checks = channel_cfg.get("required_checks", []) if isinstance(channel_cfg, dict) else []
    root = (workspace or Path.cwd()).resolve()
    results = [run_release_channel_check(root, row) for row in checks if isinstance(row, dict)]
    failed = [row for row in results if not bool(row.get("ok"))]
    migration_checks = [
        {
            "id": f"{normalized_channel}-{idx + 1}",
            "type": str(row.get("type", "unknown")),
            "path": str(row.get("path", "")),
            "status": "passed" if bool(row.get("ok")) else "failed",
            "detail": str(row.get("detail", "")),
        }
        for idx, row in enumerate(results)
    ]
    return {
        "channel": normalized_channel,
        "passed": len(failed) == 0,
        "check_count": len(results),
        "failed_count": len(failed),
        "results": results,
        "migration_checks": migration_checks,
        "config_path": str(services_module._release_channel_config_path),
        "workspace": str(root),
    }


def write_quality_report_artifact(
    services_module: Any,
    payload: dict[str, Any],
    *,
    report_path: str | None = None,
) -> str:
    if report_path:
        path = Path(report_path).expanduser()
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = services_module._quality_report_dir / f"quality-report-{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)
