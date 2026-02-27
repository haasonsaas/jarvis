"""Memory, planning, and baseline governance schema fragments."""

from __future__ import annotations

from typing import Any

SERVICE_TOOL_SCHEMAS_MEMORY: dict[str, dict[str, Any]] = {
    "memory_add": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "description": "note, profile, summary, task, etc."},
            "scope": {
                "type": "string",
                "description": "Memory scope: preferences, people, projects, or household_rules.",
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "sensitivity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "source": {"type": "string"},
            "allow_pii": {"type": "boolean"},
        },
        "required": ["text"],
    },
    "memory_update": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer"},
            "text": {"type": "string"},
            "allow_pii": {"type": "boolean"},
        },
        "required": ["memory_id", "text"],
    },
    "memory_forget": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer"},
        },
        "required": ["memory_id"],
    },
    "memory_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "max_sensitivity": {"type": "number"},
            "include_sensitive": {"type": "boolean"},
            "hybrid_weight": {"type": "number"},
            "decay_enabled": {"type": "boolean"},
            "decay_half_life_days": {"type": "number"},
            "mmr_enabled": {"type": "boolean"},
            "mmr_lambda": {"type": "number"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "scopes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
    },
    "memory_status": {
        "type": "object",
        "properties": {
            "warm": {"type": "boolean"},
            "sync": {"type": "boolean"},
            "optimize": {"type": "boolean"},
            "vacuum": {"type": "boolean"},
        },
    },
    "memory_recent": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "kind": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "scopes": {"type": "array", "items": {"type": "string"}},
        },
    },
    "memory_summary_add": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["topic", "summary"],
    },
    "memory_summary_list": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "task_plan_create": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
    },
    "task_plan_list": {
        "type": "object",
        "properties": {
            "open_only": {"type": "boolean"},
        },
    },
    "task_plan_update": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
            "step_index": {"type": "integer", "description": "0-based index"},
            "status": {"type": "string", "description": "pending, in_progress, blocked, done"},
        },
        "required": ["plan_id", "step_index", "status"],
    },
    "task_plan_summary": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
        },
        "required": ["plan_id"],
    },
    "task_plan_next": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
        },
    },
    "tool_summary": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "tool_summary_text": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
        },
    },
    "skills_list": {
        "type": "object",
        "properties": {},
    },
    "skills_enable": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
    "skills_disable": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
    "skills_version": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
}
