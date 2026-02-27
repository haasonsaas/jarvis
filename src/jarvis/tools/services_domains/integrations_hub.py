"""Integration domain service handlers extracted from services.py."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

def _services():
    from jarvis.tools import services as s

    return s


async def integration_hub(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _as_float = s._as_float
    _as_str_list = s._as_str_list
    _ha_call_service = s._ha_call_service
    _capture_note_notion = s._capture_note_notion
    _capture_note = s._capture_note
    _tool_response_text = s._tool_response_text
    _tool_response_success = s._tool_response_success
    _expansion_payload_response = s._expansion_payload_response
    _evaluate_release_channel = s._evaluate_release_channel
    _release_channel_state = s._release_channel_state
    _json_safe_clone = s._json_safe_clone
    _release_channel_config_path = s._release_channel_config_path
    _config = s._config
    slack_notify = s.slack_notify
    discord_notify = s.discord_notify
    email_send = s.email_send
    pushover_notify = s.pushover_notify
    RELEASE_CHANNELS = s.RELEASE_CHANNELS

    start_time = time.monotonic()
    if not _tool_permitted("integration_hub"):
        record_summary("integration_hub", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "calendar_upsert":
        if not _as_bool(args.get("confirm"), default=False):
            _record_service_error("integration_hub", start_time, "confirm_required")
            return {"content": [{"type": "text", "text": "calendar_upsert requires confirm=true."}]}
        event = args.get("event") if isinstance(args.get("event"), dict) else {}
        calendar_entity_id = (
            str(args.get("calendar_entity_id", "")).strip()
            or str(event.get("calendar_entity_id", "")).strip()
            or str(event.get("entity_id", "")).strip()
        ).lower()
        summary = str(args.get("summary", "")).strip() or str(event.get("summary", "")).strip()
        description = str(args.get("description", "")).strip() or str(event.get("description", "")).strip()
        location = str(args.get("location", "")).strip() or str(event.get("location", "")).strip()
        start_value = (
            str(args.get("start", "")).strip()
            or str(event.get("start_date_time", "")).strip()
            or str(event.get("start", "")).strip()
            or str(event.get("start_date", "")).strip()
        )
        end_value = (
            str(args.get("end", "")).strip()
            or str(event.get("end_date_time", "")).strip()
            or str(event.get("end", "")).strip()
            or str(event.get("end_date", "")).strip()
        )
        if not summary or not start_value or not end_value:
            _record_service_error("integration_hub", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "calendar_upsert requires summary, start, and end values."}]}
        service_data: dict[str, Any] = {"summary": summary}
        if calendar_entity_id:
            service_data["entity_id"] = calendar_entity_id
        if description:
            service_data["description"] = description
        if location:
            service_data["location"] = location
        is_all_day = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_value)) and bool(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_value)
        )
        if is_all_day:
            service_data["start_date"] = start_value
            service_data["end_date"] = end_value
        else:
            service_data["start_date_time"] = start_value
            service_data["end_date_time"] = end_value
        if _config is not None and _config.has_home_assistant:
            _, error_code = await _ha_call_service("calendar", "create_event", service_data)
            if error_code is not None:
                _record_service_error("integration_hub", start_time, error_code)
                return {"content": [{"type": "text", "text": f"calendar_upsert failed: {error_code}."}]}
            payload = {
                "action": action,
                "status": "executed",
                "provider": "home_assistant",
                "calendar_entity_id": calendar_entity_id,
                "service_data": service_data,
            }
        else:
            payload = {
                "action": action,
                "status": "drafted",
                "provider": "none",
                "service_data": service_data,
                "detail": "Home Assistant is not configured; returning draft payload.",
            }
        record_summary("integration_hub", "ok", start_time, effect="calendar_upsert", risk="medium")
        return _expansion_payload_response(payload)

    if action == "calendar_delete":
        if not _as_bool(args.get("confirm"), default=False):
            _record_service_error("integration_hub", start_time, "confirm_required")
            return {"content": [{"type": "text", "text": "calendar_delete requires confirm=true."}]}
        event_id = str(args.get("event_id", "")).strip()
        calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower()
        if not event_id:
            _record_service_error("integration_hub", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "calendar_delete requires event_id."}]}
        service_data: dict[str, Any] = {"event_id": event_id}
        if calendar_entity_id:
            service_data["entity_id"] = calendar_entity_id
        if _config is not None and _config.has_home_assistant:
            _, error_code = await _ha_call_service("calendar", "delete_event", service_data)
            if error_code is not None:
                _record_service_error("integration_hub", start_time, error_code)
                return {"content": [{"type": "text", "text": f"calendar_delete failed: {error_code}."}]}
            payload = {
                "action": action,
                "status": "executed",
                "provider": "home_assistant",
                "service_data": service_data,
            }
        else:
            payload = {
                "action": action,
                "status": "drafted",
                "provider": "none",
                "service_data": service_data,
                "detail": "Home Assistant is not configured; returning draft payload.",
            }
        record_summary("integration_hub", "ok", start_time, effect="calendar_delete", risk="high")
        return _expansion_payload_response(payload)

    if action == "notes_capture":
        backend = str(args.get("backend", "local_markdown")).strip().lower() or "local_markdown"
        title = str(args.get("title", "Jarvis Note")).strip() or "Jarvis Note"
        content = str(args.get("content", "")).strip()
        if not content:
            _record_service_error("integration_hub", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "content is required for notes_capture."}]}
        if backend == "notion":
            notion_payload, notion_error = await _capture_note_notion(title=title, content=content)
            if notion_error is None and isinstance(notion_payload, dict):
                captured = notion_payload
            elif notion_error == "missing_config":
                captured = _capture_note(
                    backend=backend,
                    title=title,
                    content=content,
                    path_hint=str(args.get("path", "")).strip(),
                )
            else:
                _record_service_error("integration_hub", start_time, notion_error or "unexpected")
                return {"content": [{"type": "text", "text": f"Notion notes_capture failed: {notion_error or 'unexpected'}."}]}
        else:
            captured = _capture_note(
                backend=backend,
                title=title,
                content=content,
                path_hint=str(args.get("path", "")).strip(),
            )
        payload = {"action": action, **captured}
        record_summary("integration_hub", "ok", start_time, effect=f"notes:{backend}", risk="low")
        return _expansion_payload_response(payload)

    if action == "messaging_flow":
        phase = str(args.get("phase", "draft")).strip().lower() or "draft"
        channel = str(args.get("channel", "slack")).strip().lower() or "slack"
        message = str(args.get("message", "")).strip()
        if phase not in {"draft", "review", "send"}:
            _record_service_error("integration_hub", start_time, "invalid_data")
            return {"content": [{"type": "text", "text": "phase must be draft|review|send."}]}
        if phase == "send" and not _as_bool(args.get("confirm"), default=False):
            _record_service_error("integration_hub", start_time, "confirm_required")
            return {"content": [{"type": "text", "text": "messaging send requires confirm=true."}]}
        payload = {
            "action": action,
            "phase": phase,
            "channel": channel,
            "message_preview": message[:200],
            "status": "queued_for_delivery" if phase == "send" else "draft_only",
        }
        if phase == "send":
            if not message:
                _record_service_error("integration_hub", start_time, "missing_fields")
                return {"content": [{"type": "text", "text": "message is required for messaging send."}]}
            base_args = dict(args)
            base_args["confirm"] = True
            if channel == "slack":
                result = await slack_notify({**base_args, "message": message})
                delivery_tool = "slack_notify"
            elif channel == "discord":
                result = await discord_notify({**base_args, "message": message})
                delivery_tool = "discord_notify"
            elif channel == "email":
                subject = str(args.get("subject", "")).strip() or "Jarvis message"
                recipient = str(args.get("to", "")).strip()
                email_args: dict[str, Any] = {**base_args, "subject": subject, "body": message, "confirm": True}
                if recipient:
                    email_args["to"] = recipient
                result = await email_send(email_args)
                delivery_tool = "email_send"
            elif channel == "pushover":
                result = await pushover_notify({**base_args, "message": message})
                delivery_tool = "pushover_notify"
            else:
                _record_service_error("integration_hub", start_time, "invalid_data")
                return {"content": [{"type": "text", "text": "channel must be one of slack|discord|email|pushover."}]}
            result_text = _tool_response_text(result)
            success = _tool_response_success(result_text)
            payload["delivery_tool"] = delivery_tool
            payload["status"] = "delivered" if success else "delivery_failed"
            payload["delivery_response"] = result_text[:240]
        record_summary("integration_hub", "ok", start_time, effect=f"messaging:{phase}", risk="medium" if phase == "send" else "low")
        return _expansion_payload_response(payload)

    if action == "commute_brief":
        traffic = args.get("traffic") if isinstance(args.get("traffic"), dict) else {}
        transit = args.get("transit") if isinstance(args.get("transit"), dict) else {}
        traffic_delay = _as_float(traffic.get("delay_min", 0.0), 0.0, minimum=0.0)
        transit_delay = _as_float(transit.get("delay_min", 0.0), 0.0, minimum=0.0)
        best_mode = "transit" if transit_delay < traffic_delay else "driving"
        payload = {
            "action": action,
            "traffic_delay_min": traffic_delay,
            "transit_delay_min": transit_delay,
            "recommended_mode": best_mode,
            "briefing": (
                f"Commute update: driving delay {traffic_delay:.0f}m, transit delay {transit_delay:.0f}m; "
                f"recommended mode is {best_mode}."
            ),
        }
        record_summary("integration_hub", "ok", start_time, effect="commute_brief", risk="low")
        return _expansion_payload_response(payload)

    if action == "shopping_orchestrate":
        items = _as_str_list(args.get("items"))
        steps = [
            {"tool": "todoist_add_task", "detail": f"Add {len(items)} shopping items"},
            {"tool": "home_assistant_todo", "detail": "Mirror list to Home Assistant household list"},
            {"tool": "pushover_notify", "detail": "Send completion/update summary"},
        ]
        payload = {"action": action, "item_count": len(items), "items": items, "orchestration_steps": steps}
        record_summary("integration_hub", "ok", start_time, effect="shopping_orchestrate", risk="low")
        return _expansion_payload_response(payload)

    if action == "research_workflow":
        if not _as_bool(args.get("allow_web"), default=False):
            _record_service_error("integration_hub", start_time, "policy")
            return {"content": [{"type": "text", "text": "research_workflow requires allow_web=true due to policy gating."}]}
        query = str(args.get("query", "")).strip()
        citations = _as_str_list(args.get("citations"))
        payload = {
            "action": action,
            "query": query,
            "status": "ready",
            "citation_count": len(citations),
            "citations": citations,
            "policy_gate": "allow_web",
        }
        record_summary("integration_hub", "ok", start_time, effect="research_workflow", risk="low")
        return _expansion_payload_response(payload)

    if action == "release_channel_get":
        payload = {
            "action": action,
            "release_channels": sorted(RELEASE_CHANNELS),
            "active_channel": str(_release_channel_state.get("active_channel", "dev")),
            "last_check_at": float(_release_channel_state.get("last_check_at", 0.0) or 0.0),
            "last_check_channel": str(_release_channel_state.get("last_check_channel", "")),
            "last_check_passed": bool(_release_channel_state.get("last_check_passed", False)),
            "migration_checks": [
                _json_safe_clone(row)
                for row in (_release_channel_state.get("migration_checks") or [])
                if isinstance(row, dict)
            ][:50],
            "release_channel_config_path": str(_release_channel_config_path),
        }
        record_summary("integration_hub", "ok", start_time, effect="release_channel_get", risk="low")
        return _expansion_payload_response(payload)

    if action == "release_channel_set":
        channel = str(args.get("channel", "")).strip().lower()
        if channel not in RELEASE_CHANNELS:
            _record_service_error("integration_hub", start_time, "invalid_data")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Unsupported channel '{channel or '<empty>'}'. Expected: dev|beta|stable.",
                    }
                ]
            }
        _release_channel_state["active_channel"] = channel
        check_result = _evaluate_release_channel(channel=channel)
        _release_channel_state["last_check_at"] = time.time()
        _release_channel_state["last_check_channel"] = channel
        _release_channel_state["last_check_passed"] = bool(check_result.get("passed", False))
        _release_channel_state["migration_checks"] = [
            _json_safe_clone(row)
            for row in (check_result.get("migration_checks") or [])
            if isinstance(row, dict)
        ][:100]
        payload = {
            "action": action,
            "active_channel": channel,
            "check": check_result,
            "release_channel_config_path": str(_release_channel_config_path),
        }
        record_summary("integration_hub", "ok", start_time, effect=f"release_channel_set:{channel}", risk="low")
        return _expansion_payload_response(payload)

    if action == "release_channel_check":
        requested_channel = str(
            args.get("channel", _release_channel_state.get("active_channel", "dev"))
        ).strip().lower() or str(_release_channel_state.get("active_channel", "dev"))
        workspace_text = str(args.get("workspace", "")).strip()
        workspace = Path(workspace_text).expanduser() if workspace_text else Path.cwd()
        if not workspace.is_absolute():
            workspace = (Path.cwd() / workspace).resolve()
        result = _evaluate_release_channel(channel=requested_channel, workspace=workspace)
        _release_channel_state["last_check_at"] = time.time()
        _release_channel_state["last_check_channel"] = requested_channel
        _release_channel_state["last_check_passed"] = bool(result.get("passed", False))
        _release_channel_state["migration_checks"] = [
            _json_safe_clone(row)
            for row in (result.get("migration_checks") or [])
            if isinstance(row, dict)
        ][:100]
        payload = {
            "action": action,
            "active_channel": str(_release_channel_state.get("active_channel", "dev")),
            **result,
        }
        record_summary(
            "integration_hub",
            "ok",
            start_time,
            effect=f"release_channel_check:{requested_channel}",
            risk="low",
        )
        return _expansion_payload_response(payload)

    _record_service_error("integration_hub", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown integration_hub action."}]}

