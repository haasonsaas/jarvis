"""Backup and restore helpers for local Jarvis state."""

from __future__ import annotations

import json
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from jarvis.config import Config

BACKUP_FORMAT_VERSION = "1.0"
DEFAULT_AUDIT_LOG_PATH = Path.home() / ".jarvis" / "audit.jsonl"
DEFAULT_OPERATOR_SETTINGS_NAME = "operator-settings.json"


def _operator_settings_path(config: Config) -> Path:
    runtime_path = Path(config.runtime_state_path).expanduser()
    return runtime_path.parent / DEFAULT_OPERATOR_SETTINGS_NAME


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _operator_settings_snapshot(config: Config) -> dict[str, Any]:
    runtime_path = Path(config.runtime_state_path).expanduser()
    runtime_payload = _load_json_file(runtime_path)
    return {
        "saved_at": time.time(),
        "operator_server": {
            "enabled": bool(config.operator_server_enabled),
            "host": str(config.operator_server_host),
            "port": int(config.operator_server_port),
            "auth_required": bool(str(config.operator_auth_token).strip()),
        },
        "runtime_controls": runtime_payload.get("runtime", {}),
        "voice_controls": runtime_payload.get("voice", {}),
        "runtime_state_path": str(runtime_path),
    }


def _target_files(config: Config, *, audit_log_path: Path) -> list[tuple[str, Path]]:
    runtime_path = Path(config.runtime_state_path).expanduser()
    audit_root = audit_log_path.expanduser()
    targets = [
        ("memory", Path(config.memory_path).expanduser()),
        ("runtime_state", runtime_path),
        ("recovery_journal", Path(config.recovery_journal_path).expanduser()),
        ("audit_log", audit_root),
        ("operator_settings", _operator_settings_path(config)),
    ]
    for idx in range(1, int(config.audit_log_backups) + 1):
        targets.append((f"audit_log_backup_{idx}", audit_root.with_name(f"{audit_root.name}.{idx}")))
    return targets


def create_backup_bundle(
    config: Config,
    destination: str | Path,
    *,
    audit_log_path: Path | None = None,
) -> dict[str, Any]:
    output_path = Path(destination).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path = DEFAULT_AUDIT_LOG_PATH if audit_log_path is None else Path(audit_log_path)
    targets = _target_files(config, audit_log_path=audit_path)

    included: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    with tarfile.open(output_path, "w:gz") as archive:
        for label, file_path in targets:
            if not file_path.exists():
                missing.append({"label": label, "path": str(file_path)})
                continue
            archive_name = f"files/{label}/{file_path.name}"
            archive.add(str(file_path), arcname=archive_name, recursive=False)
            included.append(
                {
                    "label": label,
                    "path": str(file_path),
                    "archive_name": archive_name,
                    "size_bytes": int(file_path.stat().st_size),
                }
            )

        has_operator_settings = any(item.get("label") == "operator_settings" for item in included)
        if not has_operator_settings:
            operator_member = "files/operator_settings_snapshot/operator-settings.json"
            operator_bytes = json.dumps(_operator_settings_snapshot(config), indent=2).encode("utf-8")
            operator_info = tarfile.TarInfo(name=operator_member)
            operator_info.size = len(operator_bytes)
            operator_info.mtime = time.time()
            archive.addfile(operator_info, BytesIO(operator_bytes))
            included.append(
                {
                    "label": "operator_settings_snapshot",
                    "path": "<generated>",
                    "archive_name": operator_member,
                    "size_bytes": int(len(operator_bytes)),
                }
            )

        manifest = {
            "version": BACKUP_FORMAT_VERSION,
            "created_at": time.time(),
            "included": included,
            "missing": missing,
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        manifest_info = tarfile.TarInfo(name="manifest.json")
        manifest_info.size = len(manifest_bytes)
        manifest_info.mtime = time.time()
        archive.addfile(manifest_info, BytesIO(manifest_bytes))

    return {
        "ok": True,
        "bundle_path": str(output_path),
        "included_count": len(included),
        "missing_count": len(missing),
        "included": included,
        "missing": missing,
    }


def _restore_destination(config: Config, label: str, *, audit_log_path: Path) -> Path | None:
    if label == "memory":
        return Path(config.memory_path).expanduser()
    if label == "runtime_state":
        return Path(config.runtime_state_path).expanduser()
    if label == "recovery_journal":
        return Path(config.recovery_journal_path).expanduser()
    if label == "audit_log":
        return audit_log_path.expanduser()
    if label == "operator_settings":
        return _operator_settings_path(config)
    if label.startswith("audit_log_backup_"):
        suffix = label.removeprefix("audit_log_backup_")
        return audit_log_path.expanduser().with_name(f"{audit_log_path.name}.{suffix}")
    if label == "operator_settings_snapshot":
        return _operator_settings_path(config)
    return None


def restore_backup_bundle(
    config: Config,
    source: str | Path,
    *,
    overwrite: bool = False,
    audit_log_path: Path | None = None,
) -> dict[str, Any]:
    bundle_path = Path(source).expanduser()
    if not bundle_path.exists():
        raise FileNotFoundError(f"Backup bundle not found: {bundle_path}")
    audit_path = DEFAULT_AUDIT_LOG_PATH if audit_log_path is None else Path(audit_log_path)

    restored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with tarfile.open(bundle_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = str(member.name)
            if not name.startswith("files/"):
                continue
            parts = Path(name).parts
            if len(parts) < 3:
                continue
            label = parts[1]
            target = _restore_destination(config, label, audit_log_path=audit_path)
            if target is None:
                continue
            if target.exists() and not overwrite:
                skipped.append({"label": label, "path": str(target), "reason": "exists"})
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                skipped.append({"label": label, "path": str(target), "reason": "missing_payload"})
                continue
            data = extracted.read()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            restored.append({"label": label, "path": str(target), "size_bytes": int(len(data))})

    return {
        "ok": True,
        "bundle_path": str(bundle_path),
        "restored_count": len(restored),
        "skipped_count": len(skipped),
        "restored": restored,
        "skipped": skipped,
    }
