"""Email runtime helpers for services domains."""

from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage
from typing import Any


def record_email_history(services_module: Any, *, recipient: str, subject: str) -> None:
    s = services_module
    item = {
        "timestamp": time.time(),
        "to": recipient,
        "subject": subject,
    }
    s._email_history.append(item)
    if len(s._email_history) > 200:
        del s._email_history[:-200]
    if s._memory is not None:
        try:
            s._memory.add_memory(
                f"Email sent to {recipient}: {subject}",
                kind="email_sent",
                tags=["integration", "email"],
                sensitivity=0.4,
                source="integration.email",
            )
        except Exception:
            s.log.warning("Failed to persist email send metadata", exc_info=True)


def send_email_sync(services_module: Any, *, recipient: str, subject: str, body: str) -> None:
    s = services_module
    msg = EmailMessage()
    msg["From"] = s._email_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(
        s._email_smtp_host,
        s._email_smtp_port,
        timeout=s._effective_act_timeout(s._email_timeout_sec),
    ) as smtp:
        smtp.ehlo()
        if s._email_use_tls:
            smtp.starttls()
            smtp.ehlo()
        if s._email_smtp_username:
            smtp.login(s._email_smtp_username, s._email_smtp_password)
        smtp.send_message(msg)
