"""Voice profile and control value parsing helpers for Jarvis runtime."""

from __future__ import annotations

from typing import Any


def parse_control_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return None


def parse_control_choice(value: Any, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in allowed:
        return normalized
    return None


def active_voice_user(runtime: Any) -> str:
    config = getattr(runtime, "config", None)
    user = str(getattr(config, "identity_default_user", "operator")).strip().lower()
    return user or "operator"


def active_voice_profile(
    runtime: Any,
    *,
    user: str | None,
    valid_voice_profile_verbosity: set[str],
    valid_voice_profile_confirmations: set[str],
    valid_voice_profile_pace: set[str],
    valid_voice_profile_tone: set[str],
) -> dict[str, str]:
    profile = {
        "verbosity": "normal",
        "confirmations": "standard",
        "pace": "normal",
        "tone": "auto",
    }
    key = str(user or active_voice_user(runtime)).strip().lower()
    profiles = getattr(runtime, "_voice_user_profiles", None)
    if isinstance(profiles, dict):
        raw = profiles.get(key)
        if isinstance(raw, dict):
            parse_choice = runtime._parse_control_choice
            verbosity = parse_choice(raw.get("verbosity"), valid_voice_profile_verbosity)
            confirmations = parse_choice(
                raw.get("confirmations"),
                valid_voice_profile_confirmations,
            )
            pace = parse_choice(raw.get("pace"), valid_voice_profile_pace)
            tone = parse_choice(raw.get("tone"), valid_voice_profile_tone)
            if verbosity is not None:
                profile["verbosity"] = verbosity
            if confirmations is not None:
                profile["confirmations"] = confirmations
            if pace is not None:
                profile["pace"] = pace
            if tone is not None:
                profile["tone"] = tone
    return profile


def with_voice_profile_guidance(
    runtime: Any,
    text: str,
    *,
    valid_voice_profile_verbosity: set[str],
    valid_voice_profile_confirmations: set[str],
    valid_voice_profile_pace: set[str],
    valid_voice_profile_tone: set[str],
) -> str:
    profile = active_voice_profile(
        runtime,
        user=None,
        valid_voice_profile_verbosity=valid_voice_profile_verbosity,
        valid_voice_profile_confirmations=valid_voice_profile_confirmations,
        valid_voice_profile_pace=valid_voice_profile_pace,
        valid_voice_profile_tone=valid_voice_profile_tone,
    )
    guidance: list[str] = []
    verbosity = profile.get("verbosity", "normal")
    if verbosity == "brief":
        guidance.append(
            "User voice preference: keep responses concise unless safety requires detail."
        )
    elif verbosity == "detailed":
        guidance.append("User voice preference: provide fuller detail and explicit steps.")
    tone = profile.get("tone", "auto")
    if tone == "formal":
        guidance.append(
            "User voice preference: use formal, composed phrasing and avoid slang."
        )
    elif tone == "witty":
        guidance.append(
            "User voice preference: allow occasional dry wit, but keep it brief and situational."
        )
    elif tone == "empathetic":
        guidance.append(
            "User voice preference: lead with empathy before solution steps when appropriate."
        )
    elif tone == "direct":
        guidance.append(
            "User voice preference: use direct task language with minimal social framing."
        )
    if not guidance:
        return text
    return f"{text}\n\nVoice profile preference:\n" + "\n".join(
        f"- {line}" for line in guidance
    )
