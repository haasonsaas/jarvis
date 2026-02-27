"""Audit and redaction runtime helpers for services domains."""

from __future__ import annotations

import base64
import hashlib
import json
import time
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


def audit_outcome(details: dict[str, Any]) -> str:
    policy_decision = str(details.get("policy_decision", "")).strip().lower()
    result = str(details.get("result", "")).strip().lower()
    if policy_decision in {"denied", "blocked"}:
        return "blocked"
    if policy_decision in {"allowed", "execute"}:
        return "allowed"
    if policy_decision == "dry_run":
        return "dry_run"
    if policy_decision == "preview_required":
        return "preview_required"
    if result in {"denied", "blocked"}:
        return "blocked"
    if result in {"ok", "success", "delivered"}:
        return "allowed"
    if result in {"timeout", "cancelled", "network_client_error", "http_error", "api_error", "auth", "unexpected"}:
        return "failed"
    if result in {"missing_config", "missing_fields", "invalid_data", "invalid_json"}:
        return "failed"
    if result:
        return "observed"
    return "unknown"


def audit_reason_code(details: dict[str, Any]) -> str:
    reason = str(details.get("reason", "")).strip().lower()
    if reason:
        return reason
    policy_decision = str(details.get("policy_decision", "")).strip().lower()
    if policy_decision:
        return policy_decision
    result = str(details.get("result", "")).strip().lower()
    return result


def humanize_chain_token(token: str) -> str:
    text = str(token).strip()
    if not text:
        return ""
    if text.startswith("deny:"):
        reason = text.split(":", 1)[1].replace("_", " ")
        return f"deny ({reason})"
    if text.startswith("decision:"):
        reason = text.split(":", 1)[1].replace("_", " ")
        return f"decision ({reason})"
    if text.startswith("tool="):
        return f"tool {text.split('=', 1)[1]}"
    if text.startswith("requester="):
        return f"requester {text.split('=', 1)[1]}"
    if text.startswith("profile="):
        return f"profile {text.split('=', 1)[1]}"
    return text.replace("_", " ")


def audit_decision_explanation(services_module: Any, action: str, details: dict[str, Any]) -> str:
    s = services_module
    outcome = audit_outcome(details)
    reason_code = audit_reason_code(details)
    if outcome == "blocked":
        intro = "Blocked"
    elif outcome == "allowed":
        intro = "Allowed"
    elif outcome == "dry_run":
        intro = "Dry run"
    elif outcome == "preview_required":
        intro = "Preview required"
    elif outcome == "failed":
        intro = "Failed"
    elif outcome == "observed":
        intro = "Recorded"
    else:
        intro = "Logged"

    reason_msg = s.AUDIT_REASON_MESSAGES.get(reason_code, "")
    if not reason_msg and reason_code:
        reason_msg = reason_code.replace("_", " ")

    chain = details.get("decision_chain")
    chain_tokens = chain if isinstance(chain, list) else []
    chain_hint = ""
    if chain_tokens:
        tail = [humanize_chain_token(item) for item in chain_tokens[-2:]]
        tail = [item for item in tail if item]
        if tail:
            chain_hint = f" Decision path: {' -> '.join(tail)}."

    action_label = str(action).replace("_", " ").strip() or "action"
    if reason_msg:
        return f"{intro}: {action_label} was {reason_msg}.{chain_hint}".strip()
    return f"{intro}: {action_label} was processed.{chain_hint}".strip()


def audit(services_module: Any, action: str, details: dict[str, Any]) -> None:
    s = services_module
    enriched = {str(key): value for key, value in details.items()}
    if "requester_id" not in enriched:
        enriched["requester_id"] = s._identity_default_user
    if "requester_profile" not in enriched:
        enriched["requester_profile"] = s._identity_user_profiles.get(
            str(enriched["requester_id"]).strip().lower(),
            s._identity_default_profile,
        )
    if "requester_trusted" not in enriched:
        requester = str(enriched["requester_id"]).strip().lower()
        enriched["requester_trusted"] = requester in s._identity_trusted_users or str(
            enriched["requester_profile"]
        ).strip().lower() == "trusted"
    if "speaker_verified" not in enriched:
        enriched["speaker_verified"] = False
    if "identity_source" not in enriched:
        enriched["identity_source"] = "default"
    if "decision_chain" not in enriched:
        enriched["decision_chain"] = ["identity_default_context"]
    if "decision_outcome" not in enriched:
        enriched["decision_outcome"] = audit_outcome(enriched)
    if "decision_reason" not in enriched:
        enriched["decision_reason"] = audit_reason_code(enriched)
    if "decision_explanation" not in enriched:
        enriched["decision_explanation"] = audit_decision_explanation(s, action, enriched)

    metadata_only = metadata_only_audit_details(s, action, enriched)
    redacted = redact_sensitive_for_audit(s, metadata_only)
    details_json = json.dumps(redacted, default=str)
    entry = {
        "timestamp": time.time(),
        "action": action,
        **redacted,
    }
    try:
        rotate_audit_log_if_needed(s)
        with open(s.AUDIT_LOG, "a") as handle:
            handle.write(encrypt_audit_line(s, entry) + "\n")
    except OSError as exc:
        s.log.warning("Failed to write audit log: %s", exc)
    s.log.info("AUDIT: %s — %s", action, details_json)


def rotate_audit_log_if_needed(services_module: Any) -> None:
    s = services_module
    if s._audit_log_backups < 1:
        return
    try:
        if s.AUDIT_LOG.exists() and s.AUDIT_LOG.stat().st_size >= s._audit_log_max_bytes:
            for idx in range(s._audit_log_backups, 0, -1):
                src = s.AUDIT_LOG.with_name(f"{s.AUDIT_LOG.name}.{idx}")
                dst = s.AUDIT_LOG.with_name(f"{s.AUDIT_LOG.name}.{idx + 1}")
                if src.exists():
                    if idx == s._audit_log_backups:
                        src.unlink(missing_ok=True)
                    else:
                        src.rename(dst)
            rotated = s.AUDIT_LOG.with_name(f"{s.AUDIT_LOG.name}.1")
            s.AUDIT_LOG.rename(rotated)
    except OSError as exc:
        s.log.warning("Failed to rotate audit log: %s", exc)


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
    return any(pattern.search(sample) is not None for pattern in s._PII_PATTERNS)
