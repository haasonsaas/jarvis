"""Execution flow for Home Assistant conversation tool."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_ha_conversation_execute(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    _config = s._config
    _record_service_error = s._record_service_error
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _effective_act_timeout = s._effective_act_timeout
    _ha_headers = s._ha_headers
    _recovery_operation = s._recovery_operation
    _ha_conversation_speech = s._ha_conversation_speech
    _integration_record_success = s._integration_record_success

    text = str(context.get("text", "")).strip()
    language = str(context.get("language", "")).strip()
    agent_id = str(context.get("agent_id", "")).strip()
    payload = context.get("payload") if isinstance(context.get("payload"), dict) else {"text": text}
    identity_context = context.get("identity_context")
    identity_chain = context.get("identity_chain") if isinstance(context.get("identity_chain"), list) else []

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
