"""Email history summary action handler."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def email_summary(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _email_history = s._email_history
    _memory = s._memory

    start_time = time.monotonic()
    if not _tool_permitted("email_summary"):
        record_summary("email_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    lines: list[str] = []
    if _memory is not None:
        try:
            rows = _memory.recent(limit=limit, kind="email_sent", sources=["integration.email"])
        except Exception:
            rows = []
        for entry in rows:
            lines.append(f"- {entry.text}")
    else:
        for item in list(reversed(_email_history))[:limit]:
            ts = float(item.get("timestamp", 0.0))
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            recipient = str(item.get("to", ""))
            subject = str(item.get("subject", ""))
            lines.append(f"- {when} | to={recipient} | subject={subject}")
    if not lines:
        record_summary("email_summary", "empty", start_time)
        return {"content": [{"type": "text", "text": "No email history found."}]}
    record_summary("email_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
