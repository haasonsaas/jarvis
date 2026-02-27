"""Slack notification handler."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def slack_notify(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _integration_circuit_open = s._integration_circuit_open
    _integration_circuit_open_message = s._integration_circuit_open_message
    _effective_act_timeout = s._effective_act_timeout
    _webhook_timeout_sec = s._webhook_timeout_sec
    _slack_webhook_url = s._slack_webhook_url
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _audit = s._audit
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    start_time = time.monotonic()
    if not _tool_permitted("slack_notify"):
        record_summary("slack_notify", "denied", start_time, "policy")
        _audit("slack_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("channels")
    if circuit_open:
        _record_service_error("slack_notify", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("channels", circuit_remaining)}]}
    if not _slack_webhook_url:
        _record_service_error("slack_notify", start_time, "missing_config")
        _audit("slack_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Slack webhook not configured. Set SLACK_WEBHOOK_URL."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("slack_notify", start_time, "missing_fields")
        _audit("slack_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "message is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "slack_notify",
        args,
        mutating=True,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("slack_notify", start_time, "policy")
        _audit(
            "slack_notify",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_webhook_timeout_sec, minimum=0.1, maximum=30.0))
    with _recovery_operation("slack_notify", operation="send_slack", context={"message_length": len(message)}) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(_slack_webhook_url, json={"text": message}) as resp:
                    if 200 <= resp.status < 300:
                        _integration_record_success("channels")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("slack_notify", "ok", start_time)
                        _audit(
                            "slack_notify",
                            _identity_enriched_audit(
                                {"result": "ok", "message_length": len(message)},
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        return {"content": [{"type": "text", "text": "Slack notification sent."}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("slack_notify", start_time, "auth")
                        _dead_letter_enqueue(
                            "slack_notify",
                            args,
                            reason="auth",
                            detail=f"http_status={resp.status}",
                        )
                        _audit("slack_notify", {"result": "auth", "status": resp.status})
                        return {"content": [{"type": "text", "text": "Slack webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("slack_notify", start_time, "http_error")
                    _dead_letter_enqueue(
                        "slack_notify",
                        args,
                        reason="http_error",
                        detail=f"http_status={resp.status}",
                    )
                    _audit("slack_notify", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Slack webhook error ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("slack_notify", start_time, "timeout")
            _dead_letter_enqueue("slack_notify", args, reason="timeout", detail="request timed out")
            _audit("slack_notify", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Slack webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("slack_notify", start_time, "cancelled")
            _dead_letter_enqueue("slack_notify", args, reason="cancelled", detail="request cancelled")
            _audit("slack_notify", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Slack webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("slack_notify", start_time, "network_client_error")
            _dead_letter_enqueue("slack_notify", args, reason="network_client_error", detail="client transport failure")
            _audit("slack_notify", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Slack webhook."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("slack_notify", start_time, "unexpected")
            _dead_letter_enqueue("slack_notify", args, reason="unexpected", detail="unexpected exception")
            _audit("slack_notify", {"result": "unexpected"})
            log.exception("Unexpected slack_notify failure")
            return {"content": [{"type": "text", "text": "Unexpected Slack webhook error."}]}
