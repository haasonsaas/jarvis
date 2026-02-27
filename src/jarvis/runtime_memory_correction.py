"""Runtime helpers for explicit memory correction command parsing."""

from __future__ import annotations

from typing import Any

from jarvis.runtime_constants import MEMORY_FORGET_RE, MEMORY_UPDATE_RE


def parse_memory_correction_command(text: str) -> tuple[str, dict[str, Any]] | None:
    phrase = str(text or "").strip()
    if not phrase:
        return None
    forget_match = MEMORY_FORGET_RE.fullmatch(phrase)
    if forget_match:
        memory_id = int(forget_match.group("memory_id"))
        return "memory_forget", {"memory_id": memory_id}
    update_match = MEMORY_UPDATE_RE.fullmatch(phrase)
    if update_match:
        memory_id = int(update_match.group("memory_id"))
        updated_text = update_match.group("text").strip()
        if not updated_text:
            return None
        return "memory_update", {"memory_id": memory_id, "text": updated_text}
    return None
