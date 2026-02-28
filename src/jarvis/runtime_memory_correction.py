"""Runtime helpers for explicit memory correction command parsing."""

from __future__ import annotations

from typing import Any

def parse_memory_correction_command(text: str) -> tuple[str, dict[str, Any]] | None:
    phrase = str(text or "").strip()
    if not phrase:
        return None
    tokens = phrase.split()
    if not tokens:
        return None
    lowered = [token.lower() for token in tokens]
    index = 0
    if lowered and lowered[0] == "please":
        index += 1
    if index >= len(lowered):
        return None

    forget_verbs = {"forget", "delete", "remove"}
    update_verbs = {"update", "change", "edit"}
    command = lowered[index]
    index += 1

    if command in forget_verbs:
        if index < len(lowered) and lowered[index] == "memory":
            index += 1
        if index < len(lowered) and lowered[index] == "id":
            index += 1
        if index >= len(lowered) or not lowered[index].isdigit():
            return None
        memory_id = int(lowered[index])
        index += 1
        if index != len(lowered):
            return None
        return "memory_forget", {"memory_id": memory_id}

    if command in update_verbs:
        if index < len(lowered) and lowered[index] == "memory":
            index += 1
        if index < len(lowered) and lowered[index] == "id":
            index += 1
        if index >= len(lowered) or not lowered[index].isdigit():
            return None
        memory_id = int(lowered[index])
        index += 1
        if index >= len(lowered) or lowered[index] not in {"to", "with"}:
            return None
        index += 1
        updated_text = " ".join(tokens[index:]).strip()
        if not updated_text:
            return None
        return "memory_update", {"memory_id": memory_id, "text": updated_text}
    return None
