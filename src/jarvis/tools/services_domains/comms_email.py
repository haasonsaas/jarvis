"""Email handlers for communications domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

async def email_send(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    hashlib = s.hashlib
    smtplib = s.smtplib
    log = s.log
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _integration_circuit_open = s._integration_circuit_open
    _integration_circuit_open_message = s._integration_circuit_open_message
    _as_bool = s._as_bool
    _plan_preview_require_ack = s._plan_preview_require_ack
    _preview_gate = s._preview_gate
    _email_smtp_host = s._email_smtp_host
    _email_from = s._email_from
    _email_default_to = s._email_default_to
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _audit = s._audit
    _recovery_operation = s._recovery_operation
    _send_email_sync = s._send_email_sync
    _record_email_history = s._record_email_history
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    start_time = time.monotonic()
    if not _tool_permitted("email_send"):
        record_summary("email_send", "denied", start_time, "policy")
        _audit("email_send", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("email")
    if circuit_open:
        _record_service_error("email_send", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("email", circuit_remaining)}]}
    if not _email_smtp_host or not _email_from or not _email_default_to:
        _record_service_error("email_send", start_time, "missing_config")
        _audit("email_send", {"result": "missing_config"})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Email not configured. Set EMAIL_SMTP_HOST, EMAIL_FROM, and EMAIL_DEFAULT_TO.",
                }
            ]
        }
    subject = str(args.get("subject", "")).strip()
    body = str(args.get("body", "")).strip()
    if not subject or not body:
        _record_service_error("email_send", start_time, "missing_fields")
        _audit("email_send", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "subject and body are required."}]}
    confirm = _as_bool(args.get("confirm"), default=False)
    if not confirm:
        _record_service_error("email_send", start_time, "policy")
        _audit("email_send", {"result": "denied", "reason": "confirm_required"})
        return {"content": [{"type": "text", "text": "Set confirm=true to send email."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "email_send",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("email_send", start_time, "policy")
        _audit(
            "email_send",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    recipient = str(args.get("to", "")).strip() or _email_default_to
    preview = _preview_gate(
        tool_name="email_send",
        args=args,
        risk="high",
        summary=f"email_send to {recipient} subject='{subject[:80]}'",
        signature_payload={
            "to": recipient,
            "subject": subject,
            "body_length": len(body),
            "body_digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("email_send", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "email_send",
            _identity_enriched_audit(
                {"result": "preview_required", "to": recipient, "subject_length": len(subject)},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}
    with _recovery_operation(
        "email_send",
        operation=f"send:{recipient}",
        context={"to": recipient, "subject_length": len(subject)},
    ) as recovery:
        try:
            await asyncio.to_thread(_send_email_sync, recipient=recipient, subject=subject, body=body)
        except smtplib.SMTPAuthenticationError:
            recovery.mark_failed("auth")
            _record_service_error("email_send", start_time, "auth")
            _dead_letter_enqueue("email_send", args, reason="auth", detail="smtp authentication failed")
            _audit("email_send", {"result": "auth", "to": recipient})
            return {"content": [{"type": "text", "text": "Email SMTP authentication failed."}]}
        except (smtplib.SMTPException, OSError, TimeoutError):
            recovery.mark_failed("network_client_error")
            _record_service_error("email_send", start_time, "network_client_error")
            _dead_letter_enqueue("email_send", args, reason="network_client_error", detail="smtp transport failure")
            _audit("email_send", {"result": "network_client_error", "to": recipient})
            return {"content": [{"type": "text", "text": "Failed to reach SMTP server."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("email_send", start_time, "unexpected")
            _dead_letter_enqueue("email_send", args, reason="unexpected", detail="unexpected exception")
            _audit("email_send", {"result": "unexpected", "to": recipient})
            log.exception("Unexpected email_send failure")
            return {"content": [{"type": "text", "text": "Unexpected email send error."}]}
        _integration_record_success("email")
        _record_email_history(recipient, subject)
        recovery.mark_completed(detail="ok")
        record_summary("email_send", "ok", start_time)
        _audit(
            "email_send",
            _identity_enriched_audit(
                {"result": "ok", "to": recipient, "subject_length": len(subject), "body_length": len(body)},
                identity_context,
                [*identity_chain, "decision:execute"],
            ),
        )
        return {"content": [{"type": "text", "text": f"Email sent to {recipient}."}]}

async def email_summary(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _email_history = s._email_history
    _memory = s._memory

    start_time = time.monotonic()
    if not _tool_permitted("email_summary"):
        record_summary("email_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    lines: list[str] = []
    if _memory is not None:
        try:
            rows = _memory.recent(limit=limit, kind="email_sent", sources=["integration.email"])
        except Exception:
            rows = []
        for entry in rows:
            lines.append(f"- {entry.text}")
    else:
        for item in list(reversed(_email_history))[:limit]:
            ts = float(item.get("timestamp", 0.0))
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            recipient = str(item.get("to", ""))
            subject = str(item.get("subject", ""))
            lines.append(f"- {when} | to={recipient} | subject={subject}")
    if not lines:
        record_summary("email_summary", "empty", start_time)
        return {"content": [{"type": "text", "text": "No email history found."}]}
    record_summary("email_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
