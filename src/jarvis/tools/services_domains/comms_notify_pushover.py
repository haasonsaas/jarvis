"""Pushover notification handler."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

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
