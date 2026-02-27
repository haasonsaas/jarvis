"""Audit encryption/decryption helpers for services domains."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

def configure_audit_encryption(services_module: Any, *, enabled: bool, key: str) -> None:
    s = services_module
    s._audit_encryption_enabled = bool(enabled)
    s._data_encryption_key = str(key or "").strip()
    if not s._audit_encryption_enabled:
        s._audit_fernet = None
        return
    if not s._data_encryption_key or s.Fernet is None:
        s._audit_fernet = None
        return
    candidate = s._data_encryption_key.encode("utf-8")
    try:
        s.Fernet(candidate)
        fernet_key = candidate
    except Exception:
        digest = hashlib.sha256(candidate).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
    s._audit_fernet = s.Fernet(fernet_key)


def encrypt_audit_line(services_module: Any, payload: dict[str, Any]) -> str:
    s = services_module
    line = json.dumps(payload, default=str)
    if not s._audit_encryption_enabled or s._audit_fernet is None:
        return line
    token = s._audit_fernet.encrypt(line.encode("utf-8")).decode("utf-8")
    return json.dumps({"enc": token}, default=str)


def decode_audit_line(services_module: Any, line: str) -> dict[str, Any] | None:
    s = services_module
    text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if isinstance(payload, dict) and "enc" in payload:
        token = str(payload.get("enc", "")).strip()
        if not token or s._audit_fernet is None:
            return {"encrypted": True, "error": "missing_encryption_key"}
        try:
            raw = s._audit_fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except s.InvalidToken:
            return {"encrypted": True, "error": "invalid_token"}
        try:
            decrypted = json.loads(raw)
        except Exception:
            return {"encrypted": True, "error": "invalid_payload"}
        if isinstance(decrypted, dict):
            return decrypted
        return {"encrypted": True, "error": "invalid_payload"}
    return payload if isinstance(payload, dict) else None
