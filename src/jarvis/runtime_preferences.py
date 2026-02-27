"""Preference-learning helpers for conversation-time style directives."""

from __future__ import annotations

import re

from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9']+")

_PREFERENCE_HINTS = {
    "brief",
    "concise",
    "short",
    "detailed",
    "detail",
    "verbose",
    "formal",
    "direct",
    "empathetic",
    "witty",
    "tone",
    "pace",
    "faster",
    "slower",
    "confirm",
    "confirmation",
}

_DIRECTIONAL_HINTS = {
    "please",
    "prefer",
    "could",
    "can",
    "keep",
    "use",
    "be",
    "stop",
    "dont",
    "don't",
}


def _normalized_text(text: str) -> str:
    tokens = _TOKEN_RE.findall(str(text or "").lower())
    if not tokens:
        return ""
    return " " + " ".join(tokens) + " "


def _contains_any_phrase(normalized: str, phrases: tuple[str, ...]) -> bool:
    for phrase in phrases:
        if f" {phrase} " in normalized:
            return True
    return False


def detect_voice_profile_updates(text: str) -> dict[str, str]:
    normalized = _normalized_text(text)
    if not normalized:
        return {}
    words = set(normalized.strip().split())
    if not (words & _PREFERENCE_HINTS):
        return {}
    if not (words & _DIRECTIONAL_HINTS):
        return {}

    updates: dict[str, str] = {}

    if _contains_any_phrase(
        normalized,
        (
            "more detail",
            "more detailed",
            "be detailed",
            "give detail",
            "be verbose",
            "longer answers",
            "expand answers",
        ),
    ):
        updates["verbosity"] = "detailed"
    elif _contains_any_phrase(
        normalized,
        (
            "be brief",
            "keep it brief",
            "keep brief",
            "be concise",
            "short answers",
            "less detail",
            "less detailed",
        ),
    ):
        updates["verbosity"] = "brief"

    if _contains_any_phrase(
        normalized,
        (
            "be formal",
            "more formal",
            "use formal",
            "formal tone",
        ),
    ):
        updates["tone"] = "formal"
    elif _contains_any_phrase(
        normalized,
        (
            "be direct",
            "more direct",
            "keep it direct",
        ),
    ):
        updates["tone"] = "direct"
    elif _contains_any_phrase(
        normalized,
        (
            "be empathetic",
            "more empathetic",
            "show empathy",
        ),
    ):
        updates["tone"] = "empathetic"
    elif _contains_any_phrase(
        normalized,
        (
            "be witty",
            "more witty",
            "use humor",
            "use humour",
        ),
    ):
        updates["tone"] = "witty"

    if _contains_any_phrase(
        normalized,
        (
            "speak slower",
            "talk slower",
            "slow down",
            "go slower",
        ),
    ):
        updates["pace"] = "slow"
    elif _contains_any_phrase(
        normalized,
        (
            "speak faster",
            "talk faster",
            "go faster",
            "speed up",
        ),
    ):
        updates["pace"] = "fast"

    if _contains_any_phrase(
        normalized,
        (
            "less confirmation",
            "fewer confirmations",
            "minimal confirmation",
            "dont ask for confirmation",
            "don't ask for confirmation",
        ),
    ):
        updates["confirmations"] = "minimal"
    elif _contains_any_phrase(
        normalized,
        (
            "more confirmation",
            "strict confirmation",
            "always confirm",
            "double check",
        ),
    ):
        updates["confirmations"] = "strict"

    return updates


def voice_profile_summary(profile: dict[str, Any]) -> str:
    verbosity = str(profile.get("verbosity", "normal")).strip().lower() or "normal"
    confirmations = (
        str(profile.get("confirmations", "standard")).strip().lower() or "standard"
    )
    pace = str(profile.get("pace", "normal")).strip().lower() or "normal"
    tone = str(profile.get("tone", "auto")).strip().lower() or "auto"
    return (
        f"Voice profile preference: verbosity={verbosity}; "
        f"confirmations={confirmations}; pace={pace}; tone={tone}."
    )
