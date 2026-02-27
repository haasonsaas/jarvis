"""Audit helper facade decoupled from services.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.tools.services_audit_runtime import (
    apply_retention_policies as _runtime_apply_retention_policies,
    audit as _runtime_audit,
    audit_decision_explanation as _runtime_audit_decision_explanation,
    audit_outcome as _runtime_audit_outcome,
    audit_reason_code as _runtime_audit_reason_code,
    audit_status as _runtime_audit_status,
    configure_audit_encryption as _runtime_configure_audit_encryption,
    contains_pii as _runtime_contains_pii,
    decode_audit_line as _runtime_decode_audit_line,
    encrypt_audit_line as _runtime_encrypt_audit_line,
    humanize_chain_token as _runtime_humanize_chain_token,
    metadata_only_audit_details as _runtime_metadata_only_audit_details,
    prune_audit_file as _runtime_prune_audit_file,
    redact_sensitive_for_audit as _runtime_redact_sensitive_for_audit,
    rotate_audit_log_if_needed as _runtime_rotate_audit_log_if_needed,
    sanitize_inbound_headers as _runtime_sanitize_inbound_headers,
    sanitize_inbound_payload as _runtime_sanitize_inbound_payload,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def configure_audit_encryption(*, enabled: bool, key: str) -> None:
    _runtime_configure_audit_encryption(_services_module(), enabled=enabled, key=key)


def encrypt_audit_line(payload: dict[str, Any]) -> str:
    return _runtime_encrypt_audit_line(_services_module(), payload)


def decode_audit_line(line: str) -> dict[str, Any] | None:
    return _runtime_decode_audit_line(_services_module(), line)


def audit_outcome(details: dict[str, Any]) -> str:
    return _runtime_audit_outcome(details)


def audit_reason_code(details: dict[str, Any]) -> str:
    return _runtime_audit_reason_code(details)


def humanize_chain_token(token: str) -> str:
    return _runtime_humanize_chain_token(token)


def audit_decision_explanation(action: str, details: dict[str, Any]) -> str:
    return _runtime_audit_decision_explanation(_services_module(), action, details)


def audit(action: str, details: dict[str, Any]) -> None:
    _runtime_audit(_services_module(), action, details)


def rotate_audit_log_if_needed() -> None:
    _runtime_rotate_audit_log_if_needed(_services_module())


def redact_sensitive_for_audit(value: Any, *, key_hint: str | None = None) -> Any:
    return _runtime_redact_sensitive_for_audit(_services_module(), value, key_hint=key_hint)


def metadata_only_audit_details(action: str, details: dict[str, Any]) -> dict[str, Any]:
    return _runtime_metadata_only_audit_details(_services_module(), action, details)


def sanitize_inbound_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    return _runtime_sanitize_inbound_headers(_services_module(), headers)


def sanitize_inbound_payload(value: Any, *, key_hint: str | None = None, depth: int = 0) -> Any:
    return _runtime_sanitize_inbound_payload(
        _services_module(),
        value,
        key_hint=key_hint,
        depth=depth,
    )


def contains_pii(text: str) -> bool:
    return _runtime_contains_pii(_services_module(), text)


def audit_status() -> dict[str, Any]:
    return _runtime_audit_status(_services_module())


def prune_audit_file(path: Path, *, cutoff_ts: float) -> int:
    return _runtime_prune_audit_file(_services_module(), path, cutoff_ts=cutoff_ts)


def apply_retention_policies() -> None:
    _runtime_apply_retention_policies(_services_module())
