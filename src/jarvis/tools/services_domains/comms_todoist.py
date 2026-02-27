"""Todoist handlers for communications domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

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
