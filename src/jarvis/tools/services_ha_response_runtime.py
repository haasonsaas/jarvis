"""Home Assistant response extraction helpers for services domains."""

from __future__ import annotations

from typing import Any

def ha_conversation_speech(payload: dict[str, Any]) -> str:
    response = payload.get("response")
    if not isinstance(response, dict):
        return ""
    speech = response.get("speech")
    if not isinstance(speech, dict):
        return ""
    plain = speech.get("plain")
    if isinstance(plain, dict):
        text = str(plain.get("speech", "")).strip()
        if text:
            return text
    text = str(speech.get("speech", "")).strip()
    if text:
        return text
    return ""
