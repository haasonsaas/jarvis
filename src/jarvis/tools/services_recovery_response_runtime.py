"""Response-text helpers for replay/result evaluation."""

from __future__ import annotations

from typing import Any

def tool_response_text(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return ""
    first = content[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("text", "")).strip()


def tool_response_success(text: str) -> bool:
    value = str(text).strip().lower()
    if not value:
        return False
    failure_markers = (
        "not permitted",
        "denied",
        "failed",
        "error",
        "timed out",
        "cancelled",
        "required",
        "missing",
        "not configured",
        "authentication failed",
        "invalid",
        "unexpected",
        "circuit breaker is open",
    )
    return not any(marker in value for marker in failure_markers)
