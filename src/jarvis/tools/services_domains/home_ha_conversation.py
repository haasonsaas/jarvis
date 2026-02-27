"""Home Assistant conversation handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def home_assistant_conversation(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
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
    _effective_act_timeout = s._effective_act_timeout
    _ha_headers = s._ha_headers
    _recovery_operation = s._recovery_operation
    _ha_conversation_speech = s._ha_conversation_speech
    _integration_record_success = s._integration_record_success

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_conversation"):
        record_summary("home_assistant_conversation", "denied", start_time, "policy")
        _audit("home_assistant_conversation", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_conversation", start_time, "missing_config")
        _audit("home_assistant_conversation", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("home_assistant")
    if circuit_open:
        _record_service_error("home_assistant_conversation", start_time, "circuit_open")
        _audit("home_assistant_conversation", {"result": "circuit_open"})
        return {
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
        return {
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
        return {
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
        return {"content": [{"type": "text", "text": "Conversation text is required."}]}
    if len(text) > HA_CONVERSATION_MAX_TEXT_CHARS:
        _record_service_error("home_assistant_conversation", start_time, "invalid_data")
        _audit("home_assistant_conversation", {"result": "invalid_data", "field": "text_length", "length": len(text)})
        return {
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
        return {
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
        return {"content": [{"type": "text", "text": "Set confirm=true to execute a Home Assistant conversation command."}]}
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
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
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
        return {"content": [{"type": "text", "text": preview}]}

    payload: dict[str, Any] = {"text": text}
    language = str(args.get("language", "")).strip()
    if language:
        payload["language"] = language
    agent_id = str(args.get("agent_id", "")).strip()
    if agent_id:
        payload["agent_id"] = agent_id
    url = f"{_config.hass_url}/api/conversation/process"
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(10.0))
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    with _recovery_operation(
        "home_assistant_conversation",
        operation="conversation_process",
        context={"text_length": len(text)},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        try:
                            body = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("home_assistant_conversation", start_time, "invalid_json")
                            _audit("home_assistant_conversation", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Home Assistant conversation response."}]}
                        if not isinstance(body, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("home_assistant_conversation", start_time, "invalid_json")
                            _audit("home_assistant_conversation", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Home Assistant conversation response."}]}
                        response_type = ""
                        response = body.get("response")
                        if isinstance(response, dict):
                            response_type = str(response.get("response_type", "")).strip()
                        speech = _ha_conversation_speech(body)
                        if not speech:
                            speech = "Home Assistant processed the command."
                        conversation_id = str(body.get("conversation_id", "")).strip()
                        _integration_record_success("home_assistant")
                        recovery.mark_completed(
                            detail="ok",
                            context={
                                "response_type": response_type,
                                "conversation_id": conversation_id,
                            },
                        )
                        record_summary("home_assistant_conversation", "ok", start_time)
                        _audit(
                            "home_assistant_conversation",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "response_type": response_type,
                                    "conversation_id": conversation_id,
                                    "text_length": len(text),
                                    "language": language,
                                    "agent_id": agent_id,
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        suffix = ""
                        if response_type:
                            suffix += f" [type={response_type}]"
                        if conversation_id:
                            suffix += f" [conversation_id={conversation_id}]"
                        return {"content": [{"type": "text", "text": f"{speech}{suffix}"}]}
                    if resp.status == 401:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("home_assistant_conversation", start_time, "auth")
                        _audit("home_assistant_conversation", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
                    if resp.status == 404:
                        recovery.mark_failed("not_found", context={"http_status": resp.status})
                        _record_service_error("home_assistant_conversation", start_time, "not_found")
                        _audit("home_assistant_conversation", {"result": "not_found"})
                        return {"content": [{"type": "text", "text": "Home Assistant conversation endpoint not found."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("home_assistant_conversation", start_time, "http_error")
                    _audit("home_assistant_conversation", {"result": "http_error", "status": resp.status})
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Home Assistant conversation error ({resp.status}).",
                            }
                        ]
                    }
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("home_assistant_conversation", start_time, "timeout")
            _audit("home_assistant_conversation", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Home Assistant conversation request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("home_assistant_conversation", start_time, "cancelled")
            _audit("home_assistant_conversation", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Home Assistant conversation request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("home_assistant_conversation", start_time, "network_client_error")
            _audit("home_assistant_conversation", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant conversation endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("home_assistant_conversation", start_time, "unexpected")
            _audit("home_assistant_conversation", {"result": "unexpected"})
            log.exception("Unexpected home_assistant_conversation failure")
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant conversation error."}]}

