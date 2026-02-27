"""Compatibility exports for communications domain service handlers."""

from __future__ import annotations

from jarvis.tools.services_domains.comms_email import (
    email_send,
    email_summary,
)
from jarvis.tools.services_domains.comms_notifications import (
    discord_notify,
    pushover_notify,
    slack_notify,
)
from jarvis.tools.services_domains.comms_todoist import (
    todoist_add_task,
    todoist_list_tasks,
)

__all__ = [
    "slack_notify",
    "discord_notify",
    "pushover_notify",
    "email_send",
    "email_summary",
    "todoist_add_task",
    "todoist_list_tasks",
]
