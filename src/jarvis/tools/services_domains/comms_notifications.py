"""Compatibility exports for notification handlers."""

from __future__ import annotations

from jarvis.tools.services_domains.comms_notify_pushover import pushover_notify
from jarvis.tools.services_domains.comms_notify_webhooks import (
    discord_notify,
    slack_notify,
)

__all__ = [
    "slack_notify",
    "discord_notify",
    "pushover_notify",
]
