"""Email handlers for communications domain."""

from __future__ import annotations

from jarvis.tools.services_domains.comms_email_send_action import email_send
from jarvis.tools.services_domains.comms_email_summary_action import email_summary

__all__ = ["email_send", "email_summary"]
