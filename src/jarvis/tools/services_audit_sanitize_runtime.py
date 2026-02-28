"""Audit redaction and inbound-sanitization helpers for services domains."""

from __future__ import annotations

from typing import Any

def redact_sensitive_for_audit(services_module: Any, value: Any, *, key_hint: str | None = None) -> Any:
    s = services_module
    if key_hint:
        lowered = key_hint.strip().lower()
        if any(token in lowered for token in s.SENSITIVE_AUDIT_KEY_TOKENS):
            return s.AUDIT_REDACTED
    if isinstance(value, dict):
        return {
            str(key): redact_sensitive_for_audit(s, item, key_hint=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_for_audit(s, item, key_hint=key_hint) for item in value]
    return value


def metadata_only_audit_details(
    services_module: Any,
    action: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    s = services_module
    forbidden = s.AUDIT_METADATA_ONLY_FORBIDDEN_FIELDS.get(action)
    if not forbidden:
        return {str(key): value for key, value in details.items()}
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        key_text = str(key)
        if key_text.strip().lower() in forbidden:
            continue
        sanitized[key_text] = value
    return sanitized


def sanitize_inbound_headers(services_module: Any, headers: dict[str, Any] | None) -> dict[str, str]:
    s = services_module
    sanitized: dict[str, str] = {}
    for key, value in (headers or {}).items():
        key_text = str(key)
        lowered = key_text.strip().lower()
        value_text = str(value)
        if any(token in lowered for token in s.INBOUND_REDACT_HEADER_TOKENS):
            sanitized[key_text] = s.AUDIT_REDACTED
            continue
        sanitized[key_text] = value_text
    return sanitized


def sanitize_inbound_payload(
    services_module: Any,
    value: Any,
    *,
    key_hint: str | None = None,
    depth: int = 0,
) -> Any:
    s = services_module
    if depth > 8:
        return "<max_depth>"
    if key_hint:
        lowered = key_hint.strip().lower()
        if any(token in lowered for token in s.SENSITIVE_AUDIT_KEY_TOKENS):
            return s.AUDIT_REDACTED
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= s.INBOUND_MAX_COLLECTION_ITEMS:
                out["<truncated_keys>"] = max(0, len(value) - s.INBOUND_MAX_COLLECTION_ITEMS)
                break
            key_text = str(key)
            out[key_text] = sanitize_inbound_payload(s, item, key_hint=key_text, depth=depth + 1)
        return out
    if isinstance(value, list):
        limited = value[: s.INBOUND_MAX_COLLECTION_ITEMS]
        out = [sanitize_inbound_payload(s, item, key_hint=key_hint, depth=depth + 1) for item in limited]
        if len(value) > s.INBOUND_MAX_COLLECTION_ITEMS:
            out.append(f"<truncated_items:{len(value) - s.INBOUND_MAX_COLLECTION_ITEMS}>")
        return out
    if isinstance(value, str):
        if len(value) > s.INBOUND_MAX_STRING_CHARS:
            return value[: s.INBOUND_MAX_STRING_CHARS] + "...<truncated>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    if len(text) > s.INBOUND_MAX_STRING_CHARS:
        return text[: s.INBOUND_MAX_STRING_CHARS] + "...<truncated>"
    return text


def contains_pii(services_module: Any, text: str) -> bool:
    s = services_module
    sample = text.strip()
    if not sample:
        return False
    for detector in s._PII_PATTERNS:
        if callable(detector):
            try:
                if bool(detector(sample)):
                    return True
            except Exception:
                continue
    return False
