"""Home Assistant conversation/todo/timer/area/media handlers."""

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


async def home_assistant_todo(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile
    _ha_call_service = s._ha_call_service
    _collect_json_lists_by_key = s._collect_json_lists_by_key
    _recovery_operation = s._recovery_operation

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_todo"):
        record_summary("home_assistant_todo", "denied", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_todo", start_time, "missing_config")
        _audit("home_assistant_todo", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"list", "add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "invalid_data")
        _audit("home_assistant_todo", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: list, add, remove."}]}
    if not entity_id:
        _record_service_error("home_assistant_todo", start_time, "missing_fields")
        _audit("home_assistant_todo", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_todo",
        args,
        mutating=(action in {"add", "remove"}),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit(
            "home_assistant_todo",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action in {"add", "remove"}:
        _record_service_error("home_assistant_todo", start_time, "policy")
        _audit("home_assistant_todo", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "list":
        payload, error_code = await _ha_call_service(
            "todo",
            "get_items",
            {
                "entity_id": entity_id,
                **(
                    {"status": str(args.get("status", "")).strip()}
                    if str(args.get("status", "")).strip()
                    else {}
                ),
            },
            return_response=True,
        )
        if error_code is not None:
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"To-do entity or service not found: {entity_id}"}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        items = [item for item in _collect_json_lists_by_key(payload, "items") if isinstance(item, dict)]
        if not items:
            record_summary("home_assistant_todo", "empty", start_time)
            _audit("home_assistant_todo", {"result": "empty", "action": action, "entity_id": entity_id})
            return {"content": [{"type": "text", "text": "No Home Assistant to-do items found."}]}
        lines: list[str] = []
        for item in items:
            summary = str(item.get("summary") or item.get("item") or "").strip() or "(untitled)"
            uid = str(item.get("uid") or item.get("id") or "").strip()
            status = str(item.get("status", "")).strip()
            due = str(item.get("due") or item.get("due_datetime") or "").strip()
            meta: list[str] = []
            if uid:
                meta.append(f"id={uid}")
            if status:
                meta.append(f"status={status}")
            if due:
                meta.append(f"due={due}")
            lines.append(f"- {summary}" + (f" ({'; '.join(meta)})" if meta else ""))
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {"result": "ok", "action": action, "entity_id": entity_id, "count": len(lines)},
        )
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    item = str(args.get("item", "")).strip()
    item_id = str(args.get("item_id", "")).strip()
    if action == "add":
        if not item:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item is required when action=add."}]}
        service = "add_item"
        service_data = {"entity_id": entity_id, "item": item}
        success_text = "Added Home Assistant to-do item."
    else:
        if not item and not item_id:
            _record_service_error("home_assistant_todo", start_time, "missing_fields")
            _audit("home_assistant_todo", {"result": "missing_fields", "action": action})
            return {"content": [{"type": "text", "text": "item or item_id is required when action=remove."}]}
        service = "remove_item"
        service_data = {"entity_id": entity_id, "item": item_id or item}
        success_text = "Removed Home Assistant to-do item."

    with _recovery_operation(
        "home_assistant_todo",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("todo", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_todo", start_time, error_code)
            _audit("home_assistant_todo", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant to-do entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant to-do request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant to-do service."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant to-do response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant to-do error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("home_assistant_todo", "ok", start_time)
        _audit(
            "home_assistant_todo",
            {
                "result": "ok",
                "action": action,
                "entity_id": entity_id,
                "item_length": len(item),
                "item_id": item_id,
            },
        )
        return {"content": [{"type": "text", "text": success_text}]}


async def home_assistant_timer(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    re = s.re
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_permission_profile = s._home_permission_profile
    _ha_get_state = s._ha_get_state
    _duration_seconds = s._duration_seconds
    _recovery_operation = s._recovery_operation
    _ha_call_service = s._ha_call_service

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_timer"):
        record_summary("home_assistant_timer", "denied", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_timer", start_time, "missing_config")
        _audit("home_assistant_timer", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    action = str(args.get("action", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip().lower()
    if action not in {"state", "start", "pause", "cancel", "finish"}:
        _record_service_error("home_assistant_timer", start_time, "invalid_data")
        _audit("home_assistant_timer", {"result": "invalid_data", "field": "action"})
        return {"content": [{"type": "text", "text": "Action must be one of: state, start, pause, cancel, finish."}]}
    if not entity_id:
        _record_service_error("home_assistant_timer", start_time, "missing_fields")
        _audit("home_assistant_timer", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "entity_id is required."}]}
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "home_assistant_timer",
        args,
        mutating=(action != "state"),
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit(
            "home_assistant_timer",
            _identity_enriched_audit(
                {
                    "result": "denied",
                    "reason": "identity_policy",
                    "action": action,
                    "entity_id": entity_id,
                },
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if _home_permission_profile == "readonly" and action != "state":
        _record_service_error("home_assistant_timer", start_time, "policy")
        _audit("home_assistant_timer", {"result": "denied", "reason": "readonly_profile", "action": action})
        return {"content": [{"type": "text", "text": "Home Assistant write actions are blocked in HOME_PERMISSION_PROFILE=readonly."}]}

    if action == "state":
        payload, error_code = await _ha_get_state(entity_id)
        if error_code is not None:
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": f"Timer not found: {entity_id}"}]}
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        body = payload or {}
        attributes = body.get("attributes", {}) if isinstance(body, dict) else {}
        result = {
            "entity_id": entity_id,
            "state": body.get("state", "unknown") if isinstance(body, dict) else "unknown",
            "remaining": attributes.get("remaining") if isinstance(attributes, dict) else None,
            "duration": attributes.get("duration") if isinstance(attributes, dict) else None,
            "finishes_at": attributes.get("finishes_at") if isinstance(attributes, dict) else None,
        }
        record_summary("home_assistant_timer", "ok", start_time)
        _audit("home_assistant_timer", {"result": "ok", "action": action, "entity_id": entity_id})
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    service_map = {
        "start": "start",
        "pause": "pause",
        "cancel": "cancel",
        "finish": "finish",
    }
    service_data: dict[str, Any] = {"entity_id": entity_id}
    if action == "start":
        duration_text = str(args.get("duration", "")).strip()
        if duration_text:
            duration_seconds = _duration_seconds(duration_text)
            if duration_seconds is not None:
                total = max(1, int(round(duration_seconds)))
                hours, rem = divmod(total, 3600)
                minutes, seconds = divmod(rem, 60)
                service_data["duration"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            elif re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", duration_text):
                service_data["duration"] = duration_text
            else:
                _record_service_error("home_assistant_timer", start_time, "invalid_data")
                _audit("home_assistant_timer", {"result": "invalid_data", "field": "duration"})
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "duration must be HH:MM:SS or a relative duration like 5m.",
                        }
                    ]
                }
    with _recovery_operation(
        "home_assistant_timer",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("timer", service_map[action], service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("home_assistant_timer", start_time, error_code)
            _audit("home_assistant_timer", {"result": error_code, "action": action, "entity_id": entity_id})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Home Assistant timer entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Home Assistant timer request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Home Assistant timer request was cancelled."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant timer endpoint."}]}
            if error_code == "invalid_json":
                return {"content": [{"type": "text", "text": "Invalid Home Assistant timer response."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant timer error."}]}
        recovery.mark_completed(detail="ok", context={"duration": service_data.get("duration")})
        record_summary("home_assistant_timer", "ok", start_time)
        _audit(
            "home_assistant_timer",
            {"result": "ok", "action": action, "entity_id": entity_id, "duration": service_data.get("duration")},
        )
        return {"content": [{"type": "text", "text": f"Home Assistant timer action executed: {action} on {entity_id}."}]}


async def home_assistant_area_entities(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _ha_render_template = s._ha_render_template
    _ha_get_state = s._ha_get_state

    start_time = time.monotonic()
    if not _tool_permitted("home_assistant_area_entities"):
        record_summary("home_assistant_area_entities", "denied", start_time, "policy")
        _audit("home_assistant_area_entities", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("home_assistant_area_entities", start_time, "missing_config")
        _audit("home_assistant_area_entities", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}

    area = str(args.get("area", "")).strip()
    if not area:
        _record_service_error("home_assistant_area_entities", start_time, "missing_fields")
        _audit("home_assistant_area_entities", {"result": "missing_fields"})
        return {"content": [{"type": "text", "text": "area is required."}]}
    domain_filter = str(args.get("domain", "")).strip().lower()
    include_states = _as_bool(args.get("include_states"), default=False)

    template = f"{{{{ area_entities({json.dumps(area)}) | join('\\n') }}}}"
    rendered, error_code = await _ha_render_template(template)
    if error_code is not None:
        _record_service_error("home_assistant_area_entities", start_time, error_code)
        _audit("home_assistant_area_entities", {"result": error_code, "area": area})
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Home Assistant template endpoint not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Home Assistant area lookup was cancelled."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant area lookup endpoint."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant area lookup error."}]}

    raw_entities = [line.strip().lower() for line in (rendered or "").splitlines() if line.strip()]
    entities = sorted(set(raw_entities))
    if domain_filter:
        entities = [entity for entity in entities if entity.startswith(f"{domain_filter}.")]
    if not entities:
        record_summary("home_assistant_area_entities", "empty", start_time)
        _audit(
            "home_assistant_area_entities",
            {"result": "empty", "area": area, "domain": domain_filter},
        )
        return {"content": [{"type": "text", "text": "No entities found for that area filter."}]}

    payload: dict[str, Any] = {"area": area, "domain": domain_filter or None, "entities": entities}
    if include_states:
        states: list[dict[str, Any]] = []
        for entity_id in entities[:100]:
            entity_state, state_error = await _ha_get_state(entity_id)
            if state_error is not None:
                continue
            state_payload = entity_state or {}
            attributes = state_payload.get("attributes")
            friendly_name = ""
            if isinstance(attributes, dict):
                friendly_name = str(attributes.get("friendly_name", "")).strip()
            states.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "state": state_payload.get("state", "unknown"),
                }
            )
        payload["states"] = states
    record_summary("home_assistant_area_entities", "ok", start_time)
    _audit(
        "home_assistant_area_entities",
        {
            "result": "ok",
            "area": area,
            "domain": domain_filter,
            "count": len(entities),
            "include_states": include_states,
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


async def media_control(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    math = s.math
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _config = s._config
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _as_bool = s._as_bool
    _safe_mode_enabled = s._safe_mode_enabled
    _identity_authorize = s._identity_authorize
    _identity_enriched_audit = s._identity_enriched_audit
    _home_area_policy_violation = s._home_area_policy_violation
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack
    _recovery_operation = s._recovery_operation
    _ha_call_service = s._ha_call_service

    start_time = time.monotonic()
    if not _tool_permitted("media_control"):
        record_summary("media_control", "denied", start_time, "policy")
        _audit("media_control", {"result": "denied", "reason": "policy"})
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("media_control", start_time, "missing_config")
        _audit("media_control", {"result": "missing_config"})
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    entity_id = str(args.get("entity_id", "")).strip().lower()
    action = str(args.get("action", "")).strip().lower()
    if not entity_id.startswith("media_player."):
        _record_service_error("media_control", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "entity_id must be a media_player entity."}]}
    action_map = {
        "play": ("media_play", {}),
        "pause": ("media_pause", {}),
        "turn_on": ("turn_on", {}),
        "turn_off": ("turn_off", {}),
        "toggle": ("toggle", {}),
        "mute": ("volume_mute", {"is_volume_muted": True}),
        "unmute": ("volume_mute", {"is_volume_muted": False}),
        "volume_set": ("volume_set", {}),
    }
    if action not in action_map:
        _record_service_error("media_control", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "action must be one of: play, pause, turn_on, turn_off, toggle, mute, unmute, volume_set.",
                }
            ]
        }
    service, data = action_map[action]
    payload_data = dict(data)
    if action == "volume_set":
        volume = _as_float(args.get("volume"), float("nan"))
        if not math.isfinite(volume) or volume < 0.0 or volume > 1.0:
            _record_service_error("media_control", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "volume must be a number between 0.0 and 1.0 for volume_set."}]}
        payload_data["volume_level"] = volume
    dry_run = _as_bool(args.get("dry_run"), default=False)
    safe_mode_forced = _safe_mode_enabled and not dry_run
    if safe_mode_forced:
        dry_run = True
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "media_control",
        args,
        mutating=not dry_run,
        high_risk=False,
    )
    if not identity_allowed:
        _record_service_error("media_control", start_time, "policy")
        _audit(
            "media_control",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "entity_id": entity_id, "action": action},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    if not dry_run:
        area_blocked, area_reason = _home_area_policy_violation(
            domain="media_player",
            action=service,
            entity_id=entity_id,
            data=payload_data,
        )
        if area_blocked:
            _record_service_error("media_control", start_time, "policy")
            _audit(
                "media_control",
                _identity_enriched_audit(
                    {
                        "result": "denied",
                        "reason": "area_policy",
                        "entity_id": entity_id,
                        "action": action,
                        "detail": area_reason,
                    },
                    identity_context,
                    [*identity_chain, "deny:area_policy"],
                ),
            )
            return {"content": [{"type": "text", "text": area_reason}]}
    if not dry_run:
        preview = _preview_gate(
            tool_name="media_control",
            args=args,
            risk="medium",
            summary=f"media_control {action} on {entity_id}",
            signature_payload={"entity_id": entity_id, "action": action, "payload_data": payload_data},
            enforce_default=s._plan_preview_require_ack,
        )
        if preview:
            record_summary("media_control", "dry_run", start_time, effect="plan_preview", risk="medium")
            _audit(
                "media_control",
                _identity_enriched_audit(
                    {"result": "preview_required", "entity_id": entity_id, "action": action},
                    identity_context,
                    [*identity_chain, "decision:preview_required"],
                ),
            )
            return {"content": [{"type": "text", "text": preview}]}
    if dry_run:
        record_summary("media_control", "dry_run", start_time)
        _audit(
            "media_control",
            _identity_enriched_audit(
                {
                    "result": "dry_run",
                    "entity_id": entity_id,
                    "action": action,
                    "data": payload_data,
                    "safe_mode_forced": safe_mode_forced,
                },
                identity_context,
                [*identity_chain, "decision:dry_run"],
            ),
        )
        text = f"DRY RUN: media_player.{service} on {entity_id} with {payload_data}"
        if safe_mode_forced:
            text = f"{text}. Safe mode forced dry-run."
        return {"content": [{"type": "text", "text": text}]}
    service_data = {"entity_id": entity_id, **payload_data}
    with _recovery_operation(
        "media_control",
        operation=f"{action}:{entity_id}",
        context={"entity_id": entity_id, "action": action},
    ) as recovery:
        _, error_code = await _ha_call_service("media_player", service, service_data)
        if error_code is not None:
            if error_code == "cancelled":
                recovery.mark_cancelled()
            else:
                recovery.mark_failed(error_code)
            _record_service_error("media_control", start_time, error_code)
            _audit("media_control", {"result": error_code, "entity_id": entity_id, "action": action})
            if error_code == "auth":
                return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
            if error_code == "not_found":
                return {"content": [{"type": "text", "text": "Media player entity or service not found."}]}
            if error_code == "timeout":
                return {"content": [{"type": "text", "text": "Media control request timed out."}]}
            if error_code == "cancelled":
                return {"content": [{"type": "text", "text": "Media control request was cancelled."}]}
            if error_code == "circuit_open":
                return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
            if error_code == "network_client_error":
                return {"content": [{"type": "text", "text": "Failed to reach Home Assistant media endpoint."}]}
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant media control error."}]}
        recovery.mark_completed(detail="ok")
        record_summary("media_control", "ok", start_time, effect=f"{service} {entity_id}", risk="low")
        _audit(
            "media_control",
            _identity_enriched_audit(
                {"result": "ok", "entity_id": entity_id, "action": action},
                identity_context,
                [*identity_chain, "decision:execute"],
            ),
        )
        return {"content": [{"type": "text", "text": f"Media action executed: {action} on {entity_id}."}]}
