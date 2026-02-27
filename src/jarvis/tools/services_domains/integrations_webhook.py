"""Webhook integration handlers."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def webhook_trigger(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    urlparse = s.urlparse
    _identity_context = s._identity_context
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _integration_circuit_open = s._integration_circuit_open
    _record_service_error = s._record_service_error
    _integration_circuit_open_message = s._integration_circuit_open_message
    _webhook_host_allowed = s._webhook_host_allowed
    _identity_authorize = s._identity_authorize
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack
    _webhook_auth_token = s._webhook_auth_token
    _as_float = s._as_float
    _webhook_timeout_sec = s._webhook_timeout_sec
    _effective_act_timeout = s._effective_act_timeout
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    start_time = time.monotonic()
    identity_probe = _identity_context(args)
    if not _tool_permitted("webhook_trigger"):
        record_summary("webhook_trigger", "denied", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "policy"},
                identity_probe,
                ["tool=webhook_trigger", "deny:tool_policy"],
            ),
        )
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("webhook")
    if circuit_open:
        _record_service_error("webhook_trigger", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("webhook", circuit_remaining)}]}
    url = str(args.get("url", "")).strip()
    if not url:
        _record_service_error("webhook_trigger", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "url is required."}]}
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "https_required"},
                identity_probe,
                ["tool=webhook_trigger", "deny:https_required"],
            ),
        )
        return {"content": [{"type": "text", "text": "Webhook URL must use https."}]}
    if not _webhook_host_allowed(url):
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "allowlist", "host": parsed.hostname or ""},
                identity_probe,
                ["tool=webhook_trigger", "deny:allowlist"],
            ),
        )
        return {"content": [{"type": "text", "text": "Webhook host is not in WEBHOOK_ALLOWLIST."}]}
    method = str(args.get("method", "POST")).strip().upper() or "POST"
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "method must be one of GET, POST, PUT, PATCH, DELETE."}]}
    payload = args.get("payload")
    if payload is not None and not isinstance(payload, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "payload must be an object when provided."}]}
    headers_raw = args.get("headers")
    if headers_raw is not None and not isinstance(headers_raw, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "headers must be an object when provided."}]}
    headers: dict[str, str] = {}
    for key, value in (headers_raw or {}).items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        headers[clean_key] = str(value)
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "webhook_trigger",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "method": method, "host": parsed.hostname or ""},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    preview = _preview_gate(
        tool_name="webhook_trigger",
        args=args,
        risk="high",
        summary=f"{method} {url}",
        signature_payload={"method": method, "url": url, "payload": payload or {}, "headers": headers},
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("webhook_trigger", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "preview_required", "method": method, "host": parsed.hostname or ""},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}
    if _webhook_auth_token and not any(key.lower() == "authorization" for key in headers):
        headers["Authorization"] = f"Bearer {_webhook_auth_token}"
    timeout_sec = _as_float(
        args.get("timeout_sec", _webhook_timeout_sec),
        _webhook_timeout_sec,
        minimum=0.1,
        maximum=30.0,
    )
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec, minimum=0.1, maximum=30.0))
    request_kwargs: dict[str, Any] = {"headers": headers or None}
    if method in {"POST", "PUT", "PATCH"}:
        request_kwargs["json"] = payload or {}
    with _recovery_operation(
        "webhook_trigger",
        operation=f"{method} {parsed.hostname or ''}",
        context={"method": method, "host": parsed.hostname or ""},
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
                                    "host": parsed.hostname or "",
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
                            {"result": "auth", "method": method, "host": parsed.hostname or "", "status": resp.status},
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
                        {"result": "http_error", "method": method, "host": parsed.hostname or "", "status": resp.status},
                    )
                    return {"content": [{"type": "text", "text": f"Webhook request failed ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("webhook_trigger", start_time, "timeout")
            _dead_letter_enqueue("webhook_trigger", args, reason="timeout", detail="request timed out")
            _audit("webhook_trigger", {"result": "timeout", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("webhook_trigger", start_time, "cancelled")
            _dead_letter_enqueue("webhook_trigger", args, reason="cancelled", detail="request cancelled")
            _audit("webhook_trigger", {"result": "cancelled", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("webhook_trigger", start_time, "network_client_error")
            _dead_letter_enqueue("webhook_trigger", args, reason="network_client_error", detail="client transport failure")
            _audit("webhook_trigger", {"result": "network_client_error", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Failed to reach webhook endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("webhook_trigger", start_time, "unexpected")
            _dead_letter_enqueue("webhook_trigger", args, reason="unexpected", detail="unexpected exception")
            _audit("webhook_trigger", {"result": "unexpected", "method": method, "host": parsed.hostname or ""})
            log.exception("Unexpected webhook_trigger failure")
            return {"content": [{"type": "text", "text": "Unexpected webhook trigger error."}]}

async def webhook_inbound_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _inbound_webhook_events = s._inbound_webhook_events
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_list"):
        record_summary("webhook_inbound_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    rows = list(reversed(_inbound_webhook_events))[:limit]
    record_summary("webhook_inbound_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(rows, default=str)}]}


async def webhook_inbound_clear(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _inbound_webhook_events = s._inbound_webhook_events
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_clear"):
        record_summary("webhook_inbound_clear", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    count = len(_inbound_webhook_events)
    _inbound_webhook_events.clear()
    record_summary("webhook_inbound_clear", "ok", start_time)
    _audit("webhook_inbound_clear", {"result": "ok", "cleared_count": count})
    return {"content": [{"type": "text", "text": f"Cleared inbound webhook events: {count}."}]}

