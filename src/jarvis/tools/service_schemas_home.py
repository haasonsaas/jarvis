"""Home and media tool schema fragments."""

from __future__ import annotations

from typing import Any

SERVICE_TOOL_SCHEMAS_HOME: dict[str, dict[str, Any]] = {
    "smart_home": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "HA domain: light, switch, climate, media_player, lock, cover, etc.",
            },
            "action": {
                "type": "string",
                "description": "Service to call: turn_on, turn_off, toggle, set_temperature, etc.",
            },
            "entity_id": {
                "type": "string",
                "description": "Entity ID, e.g. light.living_room, climate.thermostat.",
            },
            "data": {
                "type": "object",
                "description": "Optional service data (brightness, temperature, etc.).",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, describe what would happen without executing. "
                "Always true for locks/alarms/covers unless user explicitly confirms.",
            },
            "confirm": {"type": "boolean", "description": "Optional explicit confirmation for execute paths."},
            "requester_id": {"type": "string", "description": "Requester identity for policy decisions and audit."},
            "request_context": {"type": "object", "description": "Optional voice/text context with requester metadata."},
            "speaker_verified": {"type": "boolean", "description": "Trusted-speaker hook for voice identity pipelines."},
            "approved": {"type": "boolean", "description": "Trusted approval handshake flag for high-risk actions."},
            "approval_code": {"type": "string", "description": "Approval code for high-risk actions when required."},
            "preview_only": {"type": "boolean", "description": "Return plan preview without executing."},
            "preview_token": {"type": "string", "description": "Plan preview token required when preview acknowledgment is enforced."},
            "require_preview_ack": {"type": "boolean", "description": "If true, require preview_token before execution."},
        },
        "required": ["domain", "action", "entity_id"],
    },
    "smart_home_state": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
        },
        "required": ["entity_id"],
    },
    "home_assistant_capabilities": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "include_services": {"type": "boolean"},
        },
        "required": ["entity_id"],
    },
    "home_assistant_conversation": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Natural language command for HA conversation agent."},
            "language": {"type": "string", "description": "Optional language code (for example en)."},
            "agent_id": {"type": "string", "description": "Optional Home Assistant conversation agent id."},
            "confirm": {
                "type": "boolean",
                "description": "Must be true for execution to reduce accidental high-impact voice commands.",
            },
            "requester_id": {"type": "string", "description": "Requester identity for policy decisions and audit."},
            "request_context": {"type": "object", "description": "Optional voice/text context with requester metadata."},
            "speaker_verified": {"type": "boolean", "description": "Trusted-speaker hook for voice identity pipelines."},
            "approved": {"type": "boolean", "description": "Trusted approval handshake flag for high-risk actions."},
            "approval_code": {"type": "string", "description": "Approval code for high-risk actions when required."},
            "preview_only": {"type": "boolean", "description": "Return plan preview without executing."},
            "preview_token": {"type": "string", "description": "Plan preview token required when preview acknowledgment is enforced."},
            "require_preview_ack": {"type": "boolean", "description": "If true, require preview_token before execution."},
        },
        "required": ["text"],
    },
    "home_assistant_todo": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "list, add, or remove"},
            "entity_id": {"type": "string", "description": "Todo entity id, for example todo.shopping"},
            "item": {"type": "string", "description": "Todo item text for add/remove actions"},
            "item_id": {"type": "string", "description": "Optional uid for remove actions"},
            "status": {"type": "string", "description": "Optional status filter for list actions"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["action", "entity_id"],
    },
    "home_assistant_timer": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "state, start, pause, cancel, or finish"},
            "entity_id": {"type": "string", "description": "Timer entity id, for example timer.kitchen"},
            "duration": {"type": "string", "description": "Optional duration when action=start (HH:MM:SS)."},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
        },
        "required": ["action", "entity_id"],
    },
    "home_assistant_area_entities": {
        "type": "object",
        "properties": {
            "area": {"type": "string", "description": "Home Assistant area name."},
            "domain": {"type": "string", "description": "Optional entity domain filter (light, switch, climate, etc.)."},
            "include_states": {"type": "boolean", "description": "Include live entity states in response."},
        },
        "required": ["area"],
    },
    "media_control": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "media_player entity id"},
            "action": {"type": "string", "description": "play, pause, stop, volume_set, mute, unmute"},
            "volume": {"type": "number", "description": "Volume level between 0.0 and 1.0 for volume_set."},
            "dry_run": {"type": "boolean"},
            "requester_id": {"type": "string"},
            "request_context": {"type": "object"},
            "speaker_verified": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "approval_code": {"type": "string"},
            "preview_only": {"type": "boolean"},
            "preview_token": {"type": "string"},
            "require_preview_ack": {"type": "boolean"},
        },
        "required": ["entity_id", "action"],
    },
}
