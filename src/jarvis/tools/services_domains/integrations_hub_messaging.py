"""Messaging, commute, shopping, and research handlers for integration hub."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def integration_hub_messaging_flow(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _tool_response_text = s._tool_response_text
    _tool_response_success = s._tool_response_success
    _expansion_payload_response = s._expansion_payload_response
    slack_notify = s.slack_notify
    discord_notify = s.discord_notify
    email_send = s.email_send
    pushover_notify = s.pushover_notify

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
        "action": "messaging_flow",
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


async def integration_hub_commute_brief(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response

    traffic = args.get("traffic") if isinstance(args.get("traffic"), dict) else {}
    transit = args.get("transit") if isinstance(args.get("transit"), dict) else {}
    traffic_delay = _as_float(traffic.get("delay_min", 0.0), 0.0, minimum=0.0)
    transit_delay = _as_float(transit.get("delay_min", 0.0), 0.0, minimum=0.0)
    best_mode = "transit" if transit_delay < traffic_delay else "driving"
    payload = {
        "action": "commute_brief",
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


async def integration_hub_shopping_orchestrate(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response

    items = _as_str_list(args.get("items"))
    steps = [
        {"tool": "todoist_add_task", "detail": f"Add {len(items)} shopping items"},
        {"tool": "home_assistant_todo", "detail": "Mirror list to Home Assistant household list"},
        {"tool": "pushover_notify", "detail": "Send completion/update summary"},
    ]
    payload = {"action": "shopping_orchestrate", "item_count": len(items), "items": items, "orchestration_steps": steps}
    record_summary("integration_hub", "ok", start_time, effect="shopping_orchestrate", risk="low")
    return _expansion_payload_response(payload)


async def integration_hub_research_workflow(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response

    if not _as_bool(args.get("allow_web"), default=False):
        _record_service_error("integration_hub", start_time, "policy")
        return {"content": [{"type": "text", "text": "research_workflow requires allow_web=true due to policy gating."}]}
    query = str(args.get("query", "")).strip()
    citations = _as_str_list(args.get("citations"))
    payload = {
        "action": "research_workflow",
        "query": query,
        "status": "ready",
        "citation_count": len(citations),
        "citations": citations,
        "policy_gate": "allow_web",
    }
    record_summary("integration_hub", "ok", start_time, effect="research_workflow", risk="low")
    return _expansion_payload_response(payload)
