"""Preflight checks for Home Assistant conversation tool."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_ha_conversation_preflight(
    args: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    _audit = s._audit
    _integration_circuit_open = s._integration_circuit_open
    _integration_circuit_open_message = s._integration_circuit_open_message
    _home_conversation_enabled = s._home_conversation_enabled
    _home_conversation_permission_profile = s._home_conversation_permission_profile
    HA_CONVERSATION_MAX_TEXT_CHARS = s.HA_CONVERSATION_MAX_TEXT_CHARS
    _is_ambiguous_high_risk_text = s._is_ambiguous_high_risk_text
    _as_bool = s._as_bool
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack

    if not _tool_permitted("home_assistant_conversation"):
        record_summary("home_assistant_conversation", "denied", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "policy"})
        return None, {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_conversation", start_time, "missing_config")
        _audit("home_assistant_conversation", {"result": "missing_config"})
        return {
            "content": [
                {"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}
            ]
        }, None

    circuit_open, circuit_remaining = _integration_circuit_open("home_assistant")
    if circuit_open:
        _record_service_error("home_assistant_conversation", start_time, "circuit_open")
        _audit("home_assistant_conversation", {"result": "circuit_open"})
        return None, {
            "content": [
                {
                    "type": "text",
                    "text": _integration_circuit_open_message("home_assistant", circuit_remaining),
                }
            ]
        }
    if not _home_conversation_enabled:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "conversation_disabled"})
        return None, {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant conversation tool is disabled. Set HOME_CONVERSATION_ENABLED=true to enable.",
                }
            ]
        }
    if _home_conversation_permission_profile != "control":
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "conversation_readonly_profile"})
        return None, {
            "content": [
                {
                    "type": "text",
                    "text": "Home Assistant conversation requires HOME_CONVERSATION_PERMISSION_PROFILE=control.",
                }
            ]
        }
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("home_assistant_conversation", start_time, "missing_fields")
        _audit("home_assistant_conversation", {"result": "missing_fields"})
        return None, {"content": [{"type": "text", "text": "Conversation text is required."}]}
    if len(text) > HA_CONVERSATION_MAX_TEXT_CHARS:
        _record_service_error("home_assistant_conversation", start_time, "invalid_data")
        _audit("home_assistant_conversation", {"result": "invalid_data", "field": "text_length", "length": len(text)})
        return None, {
            "content": [
                {
                    "type": "text",
                    "text": f"Conversation text exceeds {HA_CONVERSATION_MAX_TEXT_CHARS} characters.",
                }
            ]
        }
    if _is_ambiguous_high_risk_text(text):
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "ambiguous_high_risk_text"})
        return None, {
            "content": [
                {
                    "type": "text",
                    "text": "That risky command is ambiguous. Name the exact target entity/device before execution.",
                }
            ]
        }
    confirm = _as_bool(args.get("confirm"), default=False)
    if not confirm:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "confirm_required", "text_length": len(text)})
        return None, {"content": [{"type": "text", "text": "Set confirm=true to execute a Home Assistant conversation command."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_conversation",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_conversation", start_time, "policy")
        _audit(
            "home_assistant_conversation",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "text_length": len(text)},
                identity_context,
                identity_chain,
            ),
        )
        return None, {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    preview = _preview_gate(
        tool_name="home_assistant_conversation",
        args=args,
        risk="high",
        summary=f"conversation command: {text[:120]}",
        signature_payload={
            "text": text,
            "language": str(args.get("language", "")).strip(),
            "agent_id": str(args.get("agent_id", "")).strip(),
        },
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("home_assistant_conversation", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "home_assistant_conversation",
            _identity_enriched_audit(
                {"result": "preview_required", "text_length": len(text)},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return None, {"content": [{"type": "text", "text": preview}]}

    language = str(args.get("language", "")).strip()
    agent_id = str(args.get("agent_id", "")).strip()
    payload: dict[str, Any] = {"text": text}
    if language:
        payload["language"] = language
    if agent_id:
        payload["agent_id"] = agent_id

    return {
        "text": text,
        "language": language,
        "agent_id": agent_id,
        "payload": payload,
        "identity_context": identity_context,
        "identity_chain": identity_chain,
    }, None
