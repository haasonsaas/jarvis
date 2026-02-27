"""Audit status and retention helpers for services domains."""

from __future__ import annotations

import time
from typing import Any

from jarvis.tools.services_audit_crypto_runtime import decode_audit_line

def audit_status(services_module: Any) -> dict[str, Any]:
    s = services_module
    try:
        exists = s.AUDIT_LOG.exists()
        size_bytes = s.AUDIT_LOG.stat().st_size if exists else 0
    except OSError:
        exists = False
        size_bytes = 0
    backups = []
    for idx in range(1, s._audit_log_backups + 1):
        backup_path = s.AUDIT_LOG.with_name(f"{s.AUDIT_LOG.name}.{idx}")
        try:
            if backup_path.exists():
                backups.append(
                    {
                        "path": str(backup_path),
                        "size_bytes": int(backup_path.stat().st_size),
                    }
                )
        except OSError:
            continue
    return {
        "path": str(s.AUDIT_LOG),
        "exists": exists,
        "size_bytes": int(size_bytes),
        "max_bytes": int(s._audit_log_max_bytes),
        "encrypted": bool(s._audit_encryption_enabled and s._audit_fernet is not None),
        "encryption_configured": bool(s._audit_encryption_enabled),
        "backups": backups,
        "redaction_enabled": bool(s.SENSITIVE_AUDIT_KEY_TOKENS),
        "redaction_key_count": len(s.SENSITIVE_AUDIT_KEY_TOKENS),
        "metadata_only_actions": sorted(s.AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS),
    }


def prune_audit_file(services_module: Any, path: Any, *, cutoff_ts: float) -> int:
    s = services_module
    if not path.exists():
        return 0
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return 0
    kept: list[str] = []
    removed = 0
    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue
        payload = decode_audit_line(s, raw_line)
        if not isinstance(payload, dict):
            removed += 1
            continue
        if payload.get("encrypted") is True and payload.get("error") in {
            "missing_encryption_key",
            "invalid_token",
            "invalid_payload",
        }:
            kept.append(raw_line)
            continue
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)) and float(ts) >= cutoff_ts:
            kept.append(raw_line)
        else:
            removed += 1
    if removed <= 0:
        return 0
    try:
        if kept:
            path.write_text("\n".join(kept) + "\n")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return 0
    return removed


def apply_retention_policies(services_module: Any) -> None:
    s = services_module
    now = time.time()
    if s._memory is not None and s._memory_retention_days > 0.0:
        cutoff = now - (s._memory_retention_days * 86_400.0)
        try:
            s._memory.prune_retention(cutoff_ts=cutoff)
        except Exception:
            s.log.warning("Failed to apply memory retention policy", exc_info=True)
    if s._audit_retention_days > 0.0:
        cutoff = now - (s._audit_retention_days * 86_400.0)
        paths = [s.AUDIT_LOG] + [
            s.AUDIT_LOG.with_name(f"{s.AUDIT_LOG.name}.{idx}") for idx in range(1, s._audit_log_backups + 1)
        ]
        for path in paths:
            removed = prune_audit_file(s, path, cutoff_ts=cutoff)
            if removed > 0:
                s.log.info("Applied audit retention policy to %s (removed=%d)", path, removed)
