"""Home Assistant media-control handler."""

from __future__ import annotations

import time
from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


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
