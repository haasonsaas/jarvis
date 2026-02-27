"""Execution flow for outbound webhook trigger."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def webhook_trigger_execute(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    _identity_enriched_audit = s._identity_enriched_audit
    _record_service_error = s._record_service_error
    _audit = s._audit
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    args = context.get("args") if isinstance(context.get("args"), dict) else {}
    url = str(context.get("url", "")).strip()
    parsed = context.get("parsed")
    method = str(context.get("method", "")).strip().upper()
    request_kwargs = context.get("request_kwargs") if isinstance(context.get("request_kwargs"), dict) else {}
    timeout = context.get("timeout")
    identity_context = context.get("identity_context")
    identity_chain = context.get("identity_chain") if isinstance(context.get("identity_chain"), list) else []

    with _recovery_operation(
        "webhook_trigger",
        operation=f"{method} {getattr(parsed, 'hostname', '') or ''}",
        context={"method": method, "host": getattr(parsed, 'hostname', '') or ""},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **request_kwargs) as resp:
                    body = await resp.text()
                    if 200 <= resp.status < 300:
                        _integration_record_success("webhook")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("webhook_trigger", "ok", start_time)
                        _audit(
                            "webhook_trigger",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "method": method,
                                    "host": getattr(parsed, "hostname", "") or "",
                                    "status": resp.status,
                                    "response_length": len(body),
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        body_preview = body[:200]
                        suffix = f" body={body_preview}" if body_preview else ""
                        return {"content": [{"type": "text", "text": f"Webhook delivered ({resp.status}).{suffix}"}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("webhook_trigger", start_time, "auth")
                        _dead_letter_enqueue(
                            "webhook_trigger",
                            args,
                            reason="auth",
                            detail=f"http_status={resp.status}",
                        )
                        _audit(
                            "webhook_trigger",
                            {"result": "auth", "method": method, "host": getattr(parsed, "hostname", "") or "", "status": resp.status},
                        )
                        return {"content": [{"type": "text", "text": "Webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("webhook_trigger", start_time, "http_error")
                    _dead_letter_enqueue(
                        "webhook_trigger",
                        args,
                        reason="http_error",
                        detail=f"http_status={resp.status}",
                    )
                    _audit(
                        "webhook_trigger",
                        {"result": "http_error", "method": method, "host": getattr(parsed, "hostname", "") or "", "status": resp.status},
                    )
                    return {"content": [{"type": "text", "text": f"Webhook request failed ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("webhook_trigger", start_time, "timeout")
            _dead_letter_enqueue("webhook_trigger", args, reason="timeout", detail="request timed out")
            _audit("webhook_trigger", {"result": "timeout", "method": method, "host": getattr(parsed, "hostname", "") or ""})
            return {"content": [{"type": "text", "text": "Webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("webhook_trigger", start_time, "cancelled")
            _dead_letter_enqueue("webhook_trigger", args, reason="cancelled", detail="request cancelled")
            _audit("webhook_trigger", {"result": "cancelled", "method": method, "host": getattr(parsed, "hostname", "") or ""})
            return {"content": [{"type": "text", "text": "Webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("webhook_trigger", start_time, "network_client_error")
            _dead_letter_enqueue("webhook_trigger", args, reason="network_client_error", detail="client transport failure")
            _audit("webhook_trigger", {"result": "network_client_error", "method": method, "host": getattr(parsed, "hostname", "") or ""})
            return {"content": [{"type": "text", "text": "Failed to reach webhook endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("webhook_trigger", start_time, "unexpected")
            _dead_letter_enqueue("webhook_trigger", args, reason="unexpected", detail="unexpected exception")
            _audit("webhook_trigger", {"result": "unexpected", "method": method, "host": getattr(parsed, "hostname", "") or ""})
            log.exception("Unexpected webhook_trigger failure")
            return {"content": [{"type": "text", "text": "Unexpected webhook trigger error."}]}
