"""Audit event and decision logging helpers for services domains."""

from __future__ import annotations

import json
import time
from typing import Any

from jarvis.tools.services_audit_crypto_runtime import encrypt_audit_line
from jarvis.tools.services_audit_sanitize_runtime import (
    metadata_only_audit_details,
    redact_sensitive_for_audit,
)

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

