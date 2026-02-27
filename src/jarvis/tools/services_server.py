"""MCP server/tool registration for Jarvis service handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from claude_agent_sdk import create_sdk_mcp_server, tool

from jarvis.tools.service_schemas import SERVICE_TOOL_SCHEMAS
from jarvis.tools.services_domains.comms import (
    discord_notify,
    email_send,
    email_summary,
    pushover_notify,
    slack_notify,
    todoist_add_task,
    todoist_list_tasks,
)
from jarvis.tools.services_domains.governance import (
    embodiment_presence,
    jarvis_scorecard,
    quality_evaluator,
    skills_disable,
    skills_enable,
    skills_governance,
    skills_list,
    skills_version,
    system_status,
    system_status_contract,
    tool_summary,
    tool_summary_text,
)
from jarvis.tools.services_domains.home import (
    home_assistant_area_entities,
    home_assistant_capabilities,
    home_assistant_conversation,
    home_assistant_timer,
    home_assistant_todo,
    home_orchestrator,
    media_control,
    smart_home,
    smart_home_state,
)
from jarvis.tools.services_domains.integrations import (
    calendar_events,
    calendar_next_event,
    dead_letter_list,
    dead_letter_replay,
    integration_hub,
    weather_lookup,
    webhook_inbound_clear,
    webhook_inbound_list,
    webhook_trigger,
)
from jarvis.tools.services_domains.planner import (
    planner_engine,
    reminder_complete,
    reminder_create,
    reminder_list,
    reminder_notify_due,
    task_plan_create,
    task_plan_list,
    task_plan_next,
    task_plan_summary,
    task_plan_update,
    timer_cancel,
    timer_create,
    timer_list,
)
from jarvis.tools.services_domains.trust import (
    identity_trust,
    memory_add,
    memory_forget,
    memory_governance,
    memory_recent,
    memory_search,
    memory_status,
    memory_summary_add,
    memory_summary_list,
    memory_update,
    proactive_assistant,
)

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _tool_specs() -> list[tuple[str, str, ToolHandler]]:
    from jarvis.tools import services as service_module

    return [
        (
            "smart_home",
            "Control smart home devices via Home Assistant. For destructive actions "
            "(unlock doors, disable alarms, open covers), set dry_run=true first. "
            "Always explain what you're about to do before executing.",
            smart_home,
        ),
        ("smart_home_state", "Get the current state of a Home Assistant entity.", smart_home_state),
        (
            "home_assistant_capabilities",
            "Inspect a Home Assistant entity and list available domain services for safer planning.",
            home_assistant_capabilities,
        ),
        (
            "home_assistant_conversation",
            "Send a natural language command to Home Assistant's conversation API. Requires confirm=true.",
            home_assistant_conversation,
        ),
        (
            "home_assistant_todo",
            "Manage Home Assistant to-do entities (list/add/remove).",
            home_assistant_todo,
        ),
        (
            "home_assistant_timer",
            "Control Home Assistant timer entities (state/start/pause/cancel/finish).",
            home_assistant_timer,
        ),
        (
            "home_assistant_area_entities",
            "Resolve entities in a Home Assistant area, optionally including live state.",
            home_assistant_area_entities,
        ),
        ("media_control", "Control media_player entities with a simplified action interface.", media_control),
        ("weather_lookup", "Fetch current weather using the Open-Meteo provider.", weather_lookup),
        ("webhook_trigger", "Send an outbound webhook request to an allowlisted host.", webhook_trigger),
        (
            "webhook_inbound_list",
            "List recently received inbound webhook callback events.",
            webhook_inbound_list,
        ),
        ("webhook_inbound_clear", "Clear stored inbound webhook callback events.", webhook_inbound_clear),
        ("slack_notify", "Send a Slack notification via incoming webhook.", slack_notify),
        ("discord_notify", "Send a Discord notification via webhook.", discord_notify),
        ("email_send", "Send an email through configured SMTP. Requires confirm=true.", email_send),
        ("email_summary", "Summarize recently sent emails recorded by Jarvis.", email_summary),
        (
            "dead_letter_list",
            "List dead-letter queue entries for failed outbound notifications/webhooks.",
            dead_letter_list,
        ),
        (
            "dead_letter_replay",
            "Replay failed outbound dead-letter entries by id or filter.",
            dead_letter_replay,
        ),
        (
            "todoist_add_task",
            "Create a task in Todoist (project configurable via env).",
            todoist_add_task,
        ),
        ("todoist_list_tasks", "List active tasks from Todoist.", todoist_list_tasks),
        ("pushover_notify", "Send a push notification via Pushover.", pushover_notify),
        ("get_time", "Get the current local time (device clock).", service_module.get_time),
        (
            "system_status",
            "Report current runtime capabilities and health snapshot.",
            system_status,
        ),
        (
            "system_status_contract",
            "Return the stable system_status schema contract for automation clients.",
            system_status_contract,
        ),
        (
            "jarvis_scorecard",
            "Return a unified scorecard across latency, reliability, initiative, and trust.",
            jarvis_scorecard,
        ),
        ("memory_add", "Store a long-term memory (facts, preferences, summaries).", memory_add),
        ("memory_update", "Update existing memory text by id.", memory_update),
        ("memory_forget", "Forget (delete) a memory by id.", memory_forget),
        ("memory_search", "Search long-term memory for relevant entries.", memory_search),
        ("memory_status", "Report memory index status and availability.", memory_status),
        ("memory_recent", "List recent memory entries.", memory_recent),
        (
            "memory_summary_add",
            "Store or update a short memory summary for a topic.",
            memory_summary_add,
        ),
        ("memory_summary_list", "List recent memory summaries.", memory_summary_list),
        (
            "task_plan_create",
            "Create a multi-step task plan and store it.",
            task_plan_create,
        ),
        (
            "task_plan_list",
            "List stored task plans (optionally open only).",
            task_plan_list,
        ),
        ("task_plan_update", "Update a task plan step status.", task_plan_update),
        ("task_plan_summary", "Summarize progress for a task plan.", task_plan_summary),
        ("task_plan_next", "Get the next pending step in a task plan.", task_plan_next),
        ("timer_create", "Create a countdown timer.", timer_create),
        ("timer_list", "List active timers and their remaining time.", timer_list),
        ("timer_cancel", "Cancel an active timer by id or label.", timer_cancel),
        ("reminder_create", "Create a reminder with a due time.", reminder_create),
        ("reminder_list", "List reminders and due status.", reminder_list),
        ("reminder_complete", "Mark a reminder as completed.", reminder_complete),
        (
            "reminder_notify_due",
            "Send Pushover notifications for due reminders that have not been notified yet.",
            reminder_notify_due,
        ),
        (
            "calendar_events",
            "List calendar events from Home Assistant within a time window.",
            calendar_events,
        ),
        (
            "calendar_next_event",
            "Fetch the next upcoming calendar event from Home Assistant.",
            calendar_next_event,
        ),
        ("tool_summary", "Return recent tool execution summaries (latency/outcome).", tool_summary),
        ("tool_summary_text", "Summarize recent tool executions for the user.", tool_summary_text),
        ("skills_list", "List discovered skills and their lifecycle status.", skills_list),
        ("skills_enable", "Enable a discovered skill by name.", skills_enable),
        ("skills_disable", "Disable a discovered skill by name.", skills_disable),
        ("skills_version", "Return a skill version by name.", skills_version),
        (
            "proactive_assistant",
            "Run proactive briefing/anomaly/digest workflows and follow-through queueing.",
            proactive_assistant,
        ),
        (
            "memory_governance",
            "Manage per-user memory overlays and run memory quality audits/cleanup.",
            memory_governance,
        ),
        (
            "identity_trust",
            "Manage identity confidence, trust policies, guest mode sessions, and household profiles.",
            identity_trust,
        ),
        (
            "home_orchestrator",
            "Create and execute multi-entity home plans with area policy checks and task tracking.",
            home_orchestrator,
        ),
        (
            "skills_governance",
            "Negotiate skills, inspect dependency health, enforce quotas, and run skill harness checks.",
            skills_governance,
        ),
        (
            "planner_engine",
            "Planner/executor split with task graphs, checkpoint/resume, deferred scheduling, and self-critique.",
            planner_engine,
        ),
        (
            "quality_evaluator",
            "Generate weekly quality artifacts and run deterministic evaluation datasets.",
            quality_evaluator,
        ),
        (
            "embodiment_presence",
            "Manage micro-expressions, gaze calibration, gesture envelopes, privacy posture, and motion safety envelopes.",
            embodiment_presence,
        ),
        (
            "integration_hub",
            "Run calendar/notes/messaging/commute/shopping/research orchestration workflows and release-channel operations.",
            integration_hub,
        ),
    ]


def create_services_server():
    specs = _tool_specs()
    tools = [tool(name, description, SERVICE_TOOL_SCHEMAS[name])(handler) for name, description, handler in specs]
    return create_sdk_mcp_server(
        name="jarvis-services",
        version="0.1.0",
        tools=tools,
    )
