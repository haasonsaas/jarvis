"""Communications domain service handlers extracted from services.py."""

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

async def discord_notify(args: dict[str, Any]) -> dict[str, Any]:
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
    _discord_webhook_url = s._discord_webhook_url
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _audit = s._audit
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    start_time = time.monotonic()
    if not _tool_permitted("discord_notify"):
        record_summary("discord_notify", "denied", start_time, "policy")
        _audit("discord_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("channels")
    if circuit_open:
        _record_service_error("discord_notify", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("channels", circuit_remaining)}]}
    if not _discord_webhook_url:
        _record_service_error("discord_notify", start_time, "missing_config")
        _audit("discord_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Discord webhook not configured. Set DISCORD_WEBHOOK_URL."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("discord_notify", start_time, "missing_fields")
        _audit("discord_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "message is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "discord_notify",
        args,
        mutating=True,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("discord_notify", start_time, "policy")
        _audit(
            "discord_notify",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_webhook_timeout_sec, minimum=0.1, maximum=30.0))
    with _recovery_operation("discord_notify", operation="send_discord", context={"message_length": len(message)}) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(_discord_webhook_url, json={"content": message}) as resp:
                    if 200 <= resp.status < 300:
                        _integration_record_success("channels")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("discord_notify", "ok", start_time)
                        _audit(
                            "discord_notify",
                            _identity_enriched_audit(
                                {"result": "ok", "message_length": len(message)},
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        return {"content": [{"type": "text", "text": "Discord notification sent."}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("discord_notify", start_time, "auth")
                        _dead_letter_enqueue(
                            "discord_notify",
                            args,
                            reason="auth",
                            detail=f"http_status={resp.status}",
                        )
                        _audit("discord_notify", {"result": "auth", "status": resp.status})
                        return {"content": [{"type": "text", "text": "Discord webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("discord_notify", start_time, "http_error")
                    _dead_letter_enqueue(
                        "discord_notify",
                        args,
                        reason="http_error",
                        detail=f"http_status={resp.status}",
                    )
                    _audit("discord_notify", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Discord webhook error ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("discord_notify", start_time, "timeout")
            _dead_letter_enqueue("discord_notify", args, reason="timeout", detail="request timed out")
            _audit("discord_notify", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Discord webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("discord_notify", start_time, "cancelled")
            _dead_letter_enqueue("discord_notify", args, reason="cancelled", detail="request cancelled")
            _audit("discord_notify", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Discord webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("discord_notify", start_time, "network_client_error")
            _dead_letter_enqueue(
                "discord_notify",
                args,
                reason="network_client_error",
                detail="client transport failure",
            )
            _audit("discord_notify", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": "Failed to reach Discord webhook."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("discord_notify", start_time, "unexpected")
            _dead_letter_enqueue("discord_notify", args, reason="unexpected", detail="unexpected exception")
            _audit("discord_notify", {"result": "unexpected"})
            log.exception("Unexpected discord_notify failure")
            return {"content": [{"type": "text", "text": "Unexpected Discord webhook error."}]}

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

async def todoist_add_task(args: dict[str, Any]) -> dict[str, Any]:
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
    _todoist_timeout_sec = s._todoist_timeout_sec
    _config = s._config
    _as_exact_int = s._as_exact_int
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _audit = s._audit
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success

    start_time = time.monotonic()
    if not _tool_permitted("todoist_add_task"):
        record_summary("todoist_add_task", "denied", start_time, "policy")
        _audit("todoist_add_task", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("todoist")
    if circuit_open:
        _record_service_error("todoist_add_task", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("todoist", circuit_remaining)}]}
    if not _config or not str(_config.todoist_api_token).strip():
        _record_service_error("todoist_add_task", start_time, "missing_config")
        _audit("todoist_add_task", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Todoist not configured. Set TODOIST_API_TOKEN."}]}
    content = str(args.get("content", "")).strip()
    if not content:
        _record_service_error("todoist_add_task", start_time, "missing_fields")
        _audit("todoist_add_task", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Task content required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "todoist_add_task",
        args,
        mutating=True,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("todoist_add_task", start_time, "policy")
        _audit(
            "todoist_add_task",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy"},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    payload: dict[str, Any] = {"content": content}
    description = str(args.get("description", "")).strip()
    if description:
        payload["description"] = description
    due_string = str(args.get("due_string", "")).strip()
    if due_string:
        payload["due_string"] = due_string
    priority_raw = args.get("priority", 1)
    priority = _as_exact_int(priority_raw)
    if priority is None or priority < 1 or priority > 4:
        _record_service_error("todoist_add_task", start_time, "invalid_data")
        _audit("todoist_add_task", {"result": "invalid_data", "field": "priority"})
        return {"content": [{"type": "text", "text": "Todoist priority must be an integer between 1 and 4."}]}
    payload["priority"] = priority
    labels_raw = args.get("labels")
    if labels_raw is not None:
        if not isinstance(labels_raw, list):
            _record_service_error("todoist_add_task", start_time, "invalid_data")
            _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
            return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
        labels: list[str] = []
        for item in labels_raw:
            if not isinstance(item, str):
                _record_service_error("todoist_add_task", start_time, "invalid_data")
                _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
                return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
            cleaned = item.strip()
            if not cleaned:
                _record_service_error("todoist_add_task", start_time, "invalid_data")
                _audit("todoist_add_task", {"result": "invalid_data", "field": "labels"})
                return {"content": [{"type": "text", "text": "Todoist labels must be a list of non-empty strings."}]}
            labels.append(cleaned)
        if labels:
            payload["labels"] = labels
    if str(getattr(_config, "todoist_project_id", "")).strip():
        payload["project_id"] = str(_config.todoist_project_id).strip()

    headers = {
        "Authorization": f"Bearer {str(_config.todoist_api_token).strip()}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_todoist_timeout_sec))
    with _recovery_operation("todoist_add_task", operation="create_task", context={"content_length": len(content)}) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post("https://api.todoist.com/rest/v2/tasks", headers=headers, json=payload) as resp:
                    if resp.status in {200, 201}:
                        try:
                            data = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("todoist_add_task", start_time, "invalid_json")
                            _audit("todoist_add_task", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response while creating task."}]}
                        if not isinstance(data, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("todoist_add_task", start_time, "invalid_json")
                            _audit("todoist_add_task", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response while creating task."}]}
                        task_id = data.get("id")
                        _integration_record_success("todoist")
                        recovery.mark_completed(detail="ok", context={"task_id": task_id})
                        record_summary("todoist_add_task", "ok", start_time)
                        _audit(
                            "todoist_add_task",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "task_id": task_id,
                                    "content_length": len(content),
                                    "project_id": payload.get("project_id", ""),
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        return {"content": [{"type": "text", "text": f"Todoist task created{f' (id={task_id})' if task_id else ''}."}]}
                    if resp.status == 401:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("todoist_add_task", start_time, "auth")
                        _audit("todoist_add_task", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Todoist authentication failed. Check TODOIST_API_TOKEN."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("todoist_add_task", start_time, "http_error")
                    _audit("todoist_add_task", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Todoist error ({resp.status}) creating task."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("todoist_add_task", start_time, "timeout")
            _audit("todoist_add_task", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Todoist request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("todoist_add_task", start_time, "cancelled")
            _audit("todoist_add_task", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Todoist request was cancelled."}]}
        except aiohttp.ClientError as e:
            recovery.mark_failed("network_client_error")
            _record_service_error("todoist_add_task", start_time, "network_client_error")
            _audit("todoist_add_task", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Todoist: {e}"}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("todoist_add_task", start_time, "unexpected")
            _audit("todoist_add_task", {"result": "unexpected"})
            log.exception("Unexpected todoist_add_task failure")
            return {"content": [{"type": "text", "text": "Unexpected Todoist error."}]}

async def todoist_list_tasks(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    TODOIST_LIST_MAX_RETRIES = s.TODOIST_LIST_MAX_RETRIES
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _integration_circuit_open = s._integration_circuit_open
    _integration_circuit_open_message = s._integration_circuit_open_message
    _effective_act_timeout = s._effective_act_timeout
    _todoist_timeout_sec = s._todoist_timeout_sec
    _config = s._config
    _as_exact_int = s._as_exact_int
    _as_int = s._as_int
    _retry_backoff_delay = s._retry_backoff_delay
    _audit = s._audit
    _integration_record_success = s._integration_record_success

    start_time = time.monotonic()
    if not _tool_permitted("todoist_list_tasks"):
        record_summary("todoist_list_tasks", "denied", start_time, "policy")
        _audit("todoist_list_tasks", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("todoist")
    if circuit_open:
        _record_service_error("todoist_list_tasks", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("todoist", circuit_remaining)}]}
    if not _config or not str(_config.todoist_api_token).strip():
        _record_service_error("todoist_list_tasks", start_time, "missing_config")
        _audit("todoist_list_tasks", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Todoist not configured. Set TODOIST_API_TOKEN."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    list_format = str(args.get("format", "short")).strip().lower() or "short"
    if list_format not in {"short", "verbose"}:
        _record_service_error("todoist_list_tasks", start_time, "invalid_data")
        _audit("todoist_list_tasks", {"result": "invalid_data", "field": "format"})
        return {"content": [{"type": "text", "text": "Todoist list format must be 'short' or 'verbose'."}]}
    headers = {"Authorization": f"Bearer {str(_config.todoist_api_token).strip()}"}
    params: dict[str, str] = {}
    if str(getattr(_config, "todoist_project_id", "")).strip():
        params["project_id"] = str(_config.todoist_project_id).strip()
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_todoist_timeout_sec))
    attempt = 0
    while True:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params or None) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        if not isinstance(data, list):
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        if any(not isinstance(item, dict) for item in data):
                            _record_service_error("todoist_list_tasks", start_time, "invalid_json")
                            _audit("todoist_list_tasks", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Todoist response."}]}
                        tasks = data[:limit]
                        _integration_record_success("todoist")
                        if not tasks:
                            record_summary("todoist_list_tasks", "empty", start_time)
                            _audit(
                                "todoist_list_tasks",
                                {
                                    "result": "empty",
                                    "limit": limit,
                                    "format": list_format,
                                    "project_id": params.get("project_id", ""),
                                },
                            )
                            return {"content": [{"type": "text", "text": "No Todoist tasks found."}]}

                        lines: list[str] = []
                        for task in tasks:
                            content = str(task.get("content", "")).strip() or "(untitled)"
                            if list_format == "short":
                                lines.append(f"- {content}")
                                continue
                            due_text = ""
                            due_payload = task.get("due")
                            if isinstance(due_payload, dict):
                                due_text = str(
                                    due_payload.get("string")
                                    or due_payload.get("date")
                                    or due_payload.get("datetime")
                                    or ""
                                ).strip()
                            labels = task.get("labels")
                            labels_text = ""
                            if isinstance(labels, list):
                                cleaned_labels = [str(item).strip() for item in labels if str(item).strip()]
                                if cleaned_labels:
                                    labels_text = ",".join(cleaned_labels)
                            meta: list[str] = []
                            if str(task.get("id", "")).strip():
                                meta.append(f"id={task['id']}")
                            if _as_exact_int(task.get("priority")) is not None:
                                meta.append(f"p={int(task['priority'])}")
                            if due_text:
                                meta.append(f"due={due_text}")
                            if labels_text:
                                meta.append(f"labels={labels_text}")
                            lines.append(f"- {content}" + (f" ({'; '.join(meta)})" if meta else ""))

                        record_summary("todoist_list_tasks", "ok", start_time)
                        _audit(
                            "todoist_list_tasks",
                            {
                                "result": "ok",
                                "count": len(tasks),
                                "limit": limit,
                                "format": list_format,
                                "project_id": params.get("project_id", ""),
                            },
                        )
                        return {"content": [{"type": "text", "text": "\n".join(lines)}]}
                    if resp.status == 401:
                        _record_service_error("todoist_list_tasks", start_time, "auth")
                        _audit("todoist_list_tasks", {"result": "auth"})
                        return {"content": [{"type": "text", "text": "Todoist authentication failed. Check TODOIST_API_TOKEN."}]}
                    _record_service_error("todoist_list_tasks", start_time, "http_error")
                    _audit("todoist_list_tasks", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Todoist error ({resp.status}) listing tasks."}]}
        except asyncio.TimeoutError:
            if attempt < TODOIST_LIST_MAX_RETRIES:
                await asyncio.sleep(_retry_backoff_delay(attempt))
                attempt += 1
                continue
            _record_service_error("todoist_list_tasks", start_time, "timeout")
            _audit("todoist_list_tasks", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Todoist request timed out."}]}
        except asyncio.CancelledError:
            _record_service_error("todoist_list_tasks", start_time, "cancelled")
            _audit("todoist_list_tasks", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Todoist request was cancelled."}]}
        except aiohttp.ClientError as e:
            if attempt < TODOIST_LIST_MAX_RETRIES:
                await asyncio.sleep(_retry_backoff_delay(attempt))
                attempt += 1
                continue
            _record_service_error("todoist_list_tasks", start_time, "network_client_error")
            _audit("todoist_list_tasks", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Todoist: {e}"}]}
        except Exception:
            _record_service_error("todoist_list_tasks", start_time, "unexpected")
            _audit("todoist_list_tasks", {"result": "unexpected"})
            log.exception("Unexpected todoist_list_tasks failure")
            return {"content": [{"type": "text", "text": "Unexpected Todoist error."}]}

async def pushover_notify(args: dict[str, Any]) -> dict[str, Any]:
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
    _pushover_timeout_sec = s._pushover_timeout_sec
    _config = s._config
    _as_exact_int = s._as_exact_int
    _audit = s._audit
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    start_time = time.monotonic()
    if not _tool_permitted("pushover_notify"):
        record_summary("pushover_notify", "denied", start_time, "policy")
        _audit("pushover_notify", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("pushover")
    if circuit_open:
        _record_service_error("pushover_notify", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("pushover", circuit_remaining)}]}
    if not _config or not str(_config.pushover_api_token).strip() or not str(_config.pushover_user_key).strip():
        _record_service_error("pushover_notify", start_time, "missing_config")
        _audit("pushover_notify", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Pushover not configured. Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY."}]}
    message = str(args.get("message", "")).strip()
    if not message:
        _record_service_error("pushover_notify", start_time, "missing_fields")
        _audit("pushover_notify", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "Notification message required."}]}
    title = str(args.get("title", "Jarvis")).strip() or "Jarvis"
    priority_raw = args.get("priority", 0)
    priority = _as_exact_int(priority_raw)
    if priority is None or priority < -2 or priority > 2:
        _record_service_error("pushover_notify", start_time, "invalid_data")
        _audit("pushover_notify", {"result": "invalid_data", "field": "priority"})
        return {"content": [{"type": "text", "text": "Pushover priority must be an integer between -2 and 2."}]}
    payload = {
        "token": str(_config.pushover_api_token).strip(),
        "user": str(_config.pushover_user_key).strip(),
        "message": message,
        "title": title,
        "priority": priority,
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_pushover_timeout_sec))
    with _recovery_operation(
        "pushover_notify",
        operation="send_notification",
        context={"priority": priority, "message_length": len(message)},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post("https://api.pushover.net/1/messages.json", data=payload) as resp:
                    if resp.status == 200:
                        try:
                            body = await resp.json()
                        except Exception:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("pushover_notify", start_time, "invalid_json")
                            _dead_letter_enqueue("pushover_notify", args, reason="invalid_json", detail="invalid response json")
                            _audit("pushover_notify", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                        if not isinstance(body, dict):
                            recovery.mark_failed("invalid_json")
                            _record_service_error("pushover_notify", start_time, "invalid_json")
                            _dead_letter_enqueue("pushover_notify", args, reason="invalid_json", detail="invalid response type")
                            _audit("pushover_notify", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                        status_value = _as_exact_int(body.get("status"))
                        if status_value is None:
                            recovery.mark_failed("invalid_json")
                            _record_service_error("pushover_notify", start_time, "invalid_json")
                            _dead_letter_enqueue("pushover_notify", args, reason="invalid_json", detail="missing status field")
                            _audit("pushover_notify", {"result": "invalid_json"})
                            return {"content": [{"type": "text", "text": "Invalid Pushover response."}]}
                        if status_value != 1:
                            errors = body.get("errors")
                            error_text = ""
                            if isinstance(errors, list):
                                error_text = "; ".join(str(item) for item in errors if str(item).strip())
                            recovery.mark_failed("api_error")
                            _record_service_error("pushover_notify", start_time, "api_error")
                            _dead_letter_enqueue(
                                "pushover_notify",
                                args,
                                reason="api_error",
                                detail=error_text or "api rejected notification",
                            )
                            _audit("pushover_notify", {"result": "api_error", "error": error_text})
                            return {"content": [{"type": "text", "text": f"Pushover rejected notification{f': {error_text}' if error_text else '.'}"}]}
                        _integration_record_success("pushover")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("pushover_notify", "ok", start_time)
                        _audit(
                            "pushover_notify",
                            {
                                "result": "ok",
                                "title_length": len(title),
                                "priority": priority,
                                "message_length": len(message),
                            },
                        )
                        return {"content": [{"type": "text", "text": "Notification sent."}]}
                    if resp.status in {400, 401}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("pushover_notify", start_time, "auth")
                        _dead_letter_enqueue(
                            "pushover_notify",
                            args,
                            reason="auth",
                            detail=f"http_status={resp.status}",
                        )
                        _audit("pushover_notify", {"result": "auth", "status": resp.status})
                        return {"content": [{"type": "text", "text": "Pushover authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("pushover_notify", start_time, "http_error")
                    _dead_letter_enqueue(
                        "pushover_notify",
                        args,
                        reason="http_error",
                        detail=f"http_status={resp.status}",
                    )
                    _audit("pushover_notify", {"result": "http_error", "status": resp.status})
                    return {"content": [{"type": "text", "text": f"Pushover error ({resp.status}) sending notification."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("pushover_notify", start_time, "timeout")
            _dead_letter_enqueue("pushover_notify", args, reason="timeout", detail="request timed out")
            _audit("pushover_notify", {"result": "timeout"})
            return {"content": [{"type": "text", "text": "Pushover request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("pushover_notify", start_time, "cancelled")
            _dead_letter_enqueue("pushover_notify", args, reason="cancelled", detail="request cancelled")
            _audit("pushover_notify", {"result": "cancelled"})
            return {"content": [{"type": "text", "text": "Pushover request was cancelled."}]}
        except aiohttp.ClientError as e:
            recovery.mark_failed("network_client_error")
            _record_service_error("pushover_notify", start_time, "network_client_error")
            _dead_letter_enqueue("pushover_notify", args, reason="network_client_error", detail=str(e))
            _audit("pushover_notify", {"result": "network_client_error"})
            return {"content": [{"type": "text", "text": f"Failed to reach Pushover: {e}"}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("pushover_notify", start_time, "unexpected")
            _dead_letter_enqueue("pushover_notify", args, reason="unexpected", detail="unexpected exception")
            _audit("pushover_notify", {"result": "unexpected"})
            log.exception("Unexpected pushover_notify failure")
            return {"content": [{"type": "text", "text": "Unexpected Pushover error."}]}
