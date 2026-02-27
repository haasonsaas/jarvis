"""Preflight checks for outbound webhook trigger."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def webhook_trigger_prepare(
    args: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    s = _services()
    record_summary = s.record_summary
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
    urlparse = s.urlparse
    aiohttp = s.aiohttp

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
        return None, {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("webhook")
    if circuit_open:
        _record_service_error("webhook_trigger", start_time, "circuit_open")
        return None, {"content": [{"type": "text", "text": _integration_circuit_open_message("webhook", circuit_remaining)}]}
    url = str(args.get("url", "")).strip()
    if not url:
        _record_service_error("webhook_trigger", start_time, "missing_fields")
        return None, {"content": [{"type": "text", "text": "url is required."}]}
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
        return None, {"content": [{"type": "text", "text": "Webhook URL must use https."}]}
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
        return None, {"content": [{"type": "text", "text": "Webhook host is not in WEBHOOK_ALLOWLIST."}]}
    method = str(args.get("method", "POST")).strip().upper() or "POST"
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": "method must be one of GET, POST, PUT, PATCH, DELETE."}]}
    payload = args.get("payload")
    if payload is not None and not isinstance(payload, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": "payload must be an object when provided."}]}
    headers_raw = args.get("headers")
    if headers_raw is not None and not isinstance(headers_raw, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return None, {"content": [{"type": "text", "text": "headers must be an object when provided."}]}
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
        return None, {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
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
        return None, {"content": [{"type": "text", "text": preview}]}
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

    return {
        "args": args,
        "url": url,
        "parsed": parsed,
        "method": method,
        "request_kwargs": request_kwargs,
        "timeout": timeout,
        "identity_context": identity_context,
        "identity_chain": identity_chain,
    }, None
