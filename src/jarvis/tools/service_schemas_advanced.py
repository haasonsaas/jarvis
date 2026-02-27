"""Advanced orchestration/governance schema fragments."""

from __future__ import annotations

from typing import Any

SERVICE_TOOL_SCHEMAS_ADVANCED: dict[str, dict[str, Any]] = {
    "proactive_assistant": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "briefing | anomaly_scan | routine_suggestions | "
                    "follow_through | event_digest | nudge_decision"
                ),
            },
            "mode": {"type": "string", "description": "morning or evening (for briefing)."},
            "calendar": {"type": "array", "items": {"type": "object"}},
            "reminders": {"type": "array", "items": {"type": "object"}},
            "weather": {"type": "object"},
            "home_state": {"type": "object"},
            "devices": {"type": "array", "items": {"type": "object"}},
            "history": {"type": "array", "items": {"type": "object"}},
            "opt_in": {"type": "boolean"},
            "pending_actions": {"type": "array", "items": {"type": "object"}},
            "confirm": {"type": "boolean"},
            "digest_items": {"type": "array", "items": {"type": "object"}},
            "snooze_minutes": {"type": "integer"},
            "policy": {"type": "string"},
            "quiet_window_active": {"type": "boolean"},
            "now": {"type": "number"},
            "max_dispatch": {"type": "integer"},
            "dedupe_window_sec": {"type": "number"},
            "candidates": {"type": "array", "items": {"type": "object"}},
            "context": {"type": "object"},
        },
        "required": ["action"],
    },
    "memory_governance": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "partition | quality_audit | cleanup"},
            "user": {"type": "string"},
            "shared_scopes": {"type": "array", "items": {"type": "string"}},
            "private_scopes": {"type": "array", "items": {"type": "string"}},
            "stale_days": {"type": "number"},
            "apply": {"type": "boolean"},
            "limit": {"type": "integer"},
        },
        "required": ["action"],
    },
    "identity_trust": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "session_confidence | policy_set | policy_get | guest_start | guest_validate | guest_end | household_upsert | household_list | household_remove"},
            "voice_confidence": {"type": "number"},
            "operator_hint": {"type": "string"},
            "domain": {"type": "string"},
            "required_profile": {"type": "string"},
            "requires_step_up": {"type": "boolean"},
            "guest_id": {"type": "string"},
            "guest_session_token": {"type": "string"},
            "ttl_sec": {"type": "number"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "user": {"type": "string"},
            "role": {"type": "string"},
            "trust_level": {"type": "string"},
            "exceptions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action"],
    },
    "home_orchestrator": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "plan | execute | area_policy_set | area_policy_list | automation_suggest | "
                    "automation_create | automation_apply | automation_rollback | automation_status | "
                    "task_start | task_update | task_list"
                ),
            },
            "request_text": {"type": "string"},
            "plan": {"type": "object"},
            "actions": {"type": "array", "items": {"type": "object"}},
            "area": {"type": "string"},
            "policy": {"type": "object"},
            "history": {"type": "array", "items": {"type": "object"}},
            "task_id": {"type": "string"},
            "status": {"type": "string"},
            "progress": {"type": "number"},
            "notes": {"type": "string"},
            "alias": {"type": "string"},
            "automation_id": {"type": "string"},
            "draft_id": {"type": "string"},
            "trigger": {"type": "object"},
            "condition": {"type": "array", "items": {"type": "object"}},
            "dry_run": {"type": "boolean"},
            "confirm": {"type": "boolean"},
            "ha_apply": {"type": "boolean"},
        },
        "required": ["action"],
    },
    "skills_governance": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "negotiate | dependency_health | quota_set | quota_get | quota_check | harness_run | bundle_sign | sandbox_template"},
            "requested_capabilities": {"type": "array", "items": {"type": "string"}},
            "name": {"type": "string"},
            "rate_per_min": {"type": "integer"},
            "cpu_sec": {"type": "number"},
            "outbound_calls": {"type": "integer"},
            "usage": {"type": "object"},
            "fixtures": {"type": "array", "items": {"type": "object"}},
            "bundle": {"type": "object"},
            "template": {"type": "string"},
        },
        "required": ["action"],
    },
    "planner_engine": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "plan | task_graph_create | task_graph_update | task_graph_resume | deferred_schedule | "
                    "deferred_list | self_critique | autonomy_schedule | autonomy_checkpoint | "
                    "autonomy_cycle | autonomy_status"
                ),
            },
            "goal": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}},
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
            "status": {"type": "string"},
            "title": {"type": "string"},
            "execute_at": {"type": "number"},
            "payload": {"type": "object"},
            "plan": {"type": "object"},
            "limit": {"type": "integer"},
            "risk": {"type": "string"},
            "requires_checkpoint": {"type": "boolean"},
            "checkpoint_id": {"type": "string"},
            "approved": {"type": "boolean"},
            "approved_checkpoints": {"type": "array", "items": {"type": "string"}},
            "recurrence_sec": {"type": "number"},
            "now": {"type": "number"},
        },
        "required": ["action"],
    },
    "quality_evaluator": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "weekly_report | dataset_run | reports_list"},
            "wins": {"type": "array", "items": {"type": "string"}},
            "regressions": {"type": "array", "items": {"type": "string"}},
            "report_path": {"type": "string"},
            "dataset": {"type": "array", "items": {"type": "object"}},
            "strict": {"type": "boolean"},
            "limit": {"type": "integer"},
        },
        "required": ["action"],
    },
    "embodiment_presence": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "expression_library | gaze_calibrate | gesture_profile | privacy_posture | safety_envelope | status"},
            "intent": {"type": "string"},
            "certainty_band": {"type": "string"},
            "micro_expression": {"type": "string"},
            "user": {"type": "string"},
            "distance_cm": {"type": "number"},
            "seat_offset_deg": {"type": "number"},
            "emotion": {"type": "string"},
            "importance": {"type": "string"},
            "amplitude": {"type": "number"},
            "state": {"type": "string"},
            "reason": {"type": "string"},
            "proximity_limit_cm": {"type": "number"},
            "hardware_state": {"type": "string"},
        },
        "required": ["action"],
    },
    "integration_hub": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "calendar_upsert | calendar_delete | notes_capture | messaging_flow | commute_brief | "
                    "shopping_orchestrate | research_workflow | release_channel_get | release_channel_set | "
                    "release_channel_check"
                ),
            },
            "confirm": {"type": "boolean"},
            "event_id": {"type": "string"},
            "event": {"type": "object"},
            "backend": {"type": "string"},
            "path": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "calendar_entity_id": {"type": "string"},
            "start": {"type": "string"},
            "end": {"type": "string"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "event_payload": {"type": "object"},
            "channel": {"type": "string"},
            "phase": {"type": "string"},
            "message": {"type": "string"},
            "subject": {"type": "string"},
            "to": {"type": "string"},
            "traffic": {"type": "object"},
            "transit": {"type": "object"},
            "items": {"type": "array", "items": {"type": "string"}},
            "allow_web": {"type": "boolean"},
            "query": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "string"}},
            "workspace": {"type": "string"},
        },
        "required": ["action"],
    },
}
