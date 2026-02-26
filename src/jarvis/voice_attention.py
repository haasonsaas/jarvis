from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


VALID_WAKE_MODES = {"always_listening", "wake_word", "push_to_talk"}
VALID_TIMEOUT_PROFILES = {"short", "normal", "long"}

_CONFIRM_WORDS = {
    "confirm",
    "yes",
    "yeah",
    "yep",
    "yup",
    "affirm",
    "affirmative",
    "do it",
    "go ahead",
}
_DENY_WORDS = {
    "deny",
    "no",
    "nope",
    "nah",
    "cancel",
    "stop",
    "negative",
    "dont",
    "don't",
}
_REPEAT_WORDS = {
    "repeat",
    "again",
    "say again",
    "repeat that",
}


@dataclass
class TranscriptDecision:
    accepted: bool
    text: str
    reason: str
    reply: str | None = None


@dataclass
class VoiceAttentionConfig:
    wake_words: list[str]
    mode: str = "always_listening"
    wake_word_sensitivity: float = 0.82
    followup_window_sec: float = 6.0
    timeout_profile: str = "normal"
    timeout_short_sec: float = 0.55
    timeout_normal_sec: float = 0.8
    timeout_long_sec: float = 1.2
    barge_threshold_always_listening: float = 0.4
    barge_threshold_wake_word: float = 0.45
    barge_threshold_push_to_talk: float = 0.5
    min_post_wake_chars: int = 4
    room_default: str = "main"


class VoiceAttentionController:
    """Controls wake-word/mode routing and voice attention state transitions."""

    def __init__(self, config: VoiceAttentionConfig) -> None:
        self._wake_words = [word.strip().lower() for word in config.wake_words if word.strip()]
        if not self._wake_words:
            self._wake_words = ["jarvis"]

        self.mode = self._normalize_mode(config.mode)
        self.wake_word_sensitivity = self._normalize_sensitivity(config.wake_word_sensitivity)
        self.followup_window_sec = max(0.0, float(config.followup_window_sec))
        self.timeout_profile = self._normalize_timeout_profile(config.timeout_profile)

        self.timeout_profiles = {
            "short": max(0.2, float(config.timeout_short_sec)),
            "normal": max(0.2, float(config.timeout_normal_sec)),
            "long": max(0.2, float(config.timeout_long_sec)),
        }
        self.barge_thresholds = {
            "always_listening": self._normalize_threshold(config.barge_threshold_always_listening, 0.4),
            "wake_word": self._normalize_threshold(config.barge_threshold_wake_word, 0.45),
            "push_to_talk": self._normalize_threshold(config.barge_threshold_push_to_talk, 0.5),
        }
        self.min_post_wake_chars = max(1, int(config.min_post_wake_chars))
        self.active_room = (config.room_default or "main").strip().lower() or "main"

        self.push_to_talk_active = False
        self.sleeping = False
        self.followup_until = 0.0
        self.last_wake_word = ""
        self.last_wake_time = 0.0

        self.accepted_count = 0
        self.rejected_count = 0
        self.false_positive_count = 0

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        candidate = (mode or "always_listening").strip().lower()
        return candidate if candidate in VALID_WAKE_MODES else "always_listening"

    @staticmethod
    def _normalize_timeout_profile(profile: str) -> str:
        candidate = (profile or "normal").strip().lower()
        return candidate if candidate in VALID_TIMEOUT_PROFILES else "normal"

    @staticmethod
    def _normalize_sensitivity(value: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.82
        if not math.isfinite(parsed):
            return 0.82
        return max(0.5, min(0.99, parsed))

    @staticmethod
    def _normalize_threshold(value: float, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return max(0.05, min(0.95, parsed))

    def set_mode(self, mode: str) -> str:
        self.mode = self._normalize_mode(mode)
        if self.mode != "wake_word":
            self.sleeping = False
        return self.mode

    def set_timeout_profile(self, profile: str) -> str:
        self.timeout_profile = self._normalize_timeout_profile(profile)
        return self.timeout_profile

    def set_push_to_talk_active(self, active: bool) -> None:
        self.push_to_talk_active = bool(active)

    def silence_timeout(self) -> float:
        return float(self.timeout_profiles.get(self.timeout_profile, self.timeout_profiles["normal"]))

    def barge_in_threshold(self) -> float:
        return float(self.barge_thresholds.get(self.mode, 0.4))

    def continue_listening(self, *, now: float | None = None, window_sec: float | None = None) -> None:
        base = time.monotonic() if now is None else float(now)
        window = self.followup_window_sec if window_sec is None else max(0.0, float(window_sec))
        self.followup_until = base + window

    def update_room_from_doa(self, doa_angle: float | None) -> None:
        if doa_angle is None:
            return
        angle = float(doa_angle)
        if angle <= -35.0:
            self.active_room = "left"
        elif angle >= 35.0:
            self.active_room = "right"
        else:
            self.active_room = "center"

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(a=a, b=b).ratio()

    def _detect_wake_word(self, text: str) -> tuple[bool, str, str]:
        compact = re.sub(r"\s+", " ", text.strip().lower())
        if not compact:
            return False, "", ""
        for wake_word in self._wake_words:
            wake_compact = re.sub(r"\s+", " ", wake_word)
            prefix = compact[: len(wake_compact)]
            if self._similarity(prefix, wake_compact) >= self.wake_word_sensitivity:
                remainder = compact[len(wake_compact) :].lstrip(" ,.!?:;")
                return True, wake_word, remainder
        return False, "", ""

    def _consume_voice_command(self, text: str) -> TranscriptDecision | None:
        normalized = text.strip().lower()
        if normalized in {"jarvis sleep", "sleep mode", "go to sleep"}:
            self.sleeping = True
            self.rejected_count += 1
            return TranscriptDecision(False, "", "sleep_mode_enabled", "Entering sleep mode.")
        if normalized in {"jarvis wake", "wake up", "wake mode"}:
            self.sleeping = False
            self.continue_listening()
            self.rejected_count += 1
            return TranscriptDecision(False, "", "sleep_mode_disabled", "Wake mode enabled.")
        if normalized in {"always listening mode", "mode always listening"}:
            self.set_mode("always_listening")
            self.rejected_count += 1
            return TranscriptDecision(False, "", "mode_changed", "Mode set to always listening.")
        if normalized in {"wake word mode", "mode wake word"}:
            self.set_mode("wake_word")
            self.rejected_count += 1
            return TranscriptDecision(False, "", "mode_changed", "Mode set to wake word.")
        if normalized in {"push to talk mode", "mode push to talk"}:
            self.set_mode("push_to_talk")
            self.rejected_count += 1
            return TranscriptDecision(False, "", "mode_changed", "Mode set to push to talk.")
        return None

    def process_transcript(self, text: str, *, now: float | None = None) -> TranscriptDecision:
        timestamp = time.monotonic() if now is None else float(now)
        raw = text.strip()
        if not raw:
            self.rejected_count += 1
            return TranscriptDecision(False, "", "empty")

        command = self._consume_voice_command(raw)
        if command is not None:
            return command

        if self.mode == "always_listening":
            self.accepted_count += 1
            self.continue_listening(now=timestamp)
            return TranscriptDecision(True, raw, "accepted_always")

        if self.mode == "push_to_talk":
            if self.push_to_talk_active or timestamp < self.followup_until:
                self.accepted_count += 1
                self.continue_listening(now=timestamp)
                return TranscriptDecision(True, raw, "accepted_push_to_talk")
            self.rejected_count += 1
            return TranscriptDecision(False, "", "push_to_talk_inactive")

        # wake_word mode
        if self.sleeping and timestamp >= self.followup_until:
            detected, wake_word, remainder = self._detect_wake_word(raw)
            if not detected:
                self.rejected_count += 1
                return TranscriptDecision(False, "", "sleeping")
            self.sleeping = False
            self.last_wake_word = wake_word
            self.last_wake_time = timestamp
            self.continue_listening(now=timestamp)
            if len(remainder) < self.min_post_wake_chars:
                self.rejected_count += 1
                self.false_positive_count += 1
                return TranscriptDecision(False, "", "wake_word_only", "Yes?")
            self.accepted_count += 1
            return TranscriptDecision(True, remainder, "accepted_wake_word")

        if timestamp < self.followup_until:
            self.accepted_count += 1
            self.continue_listening(now=timestamp)
            return TranscriptDecision(True, raw, "accepted_followup")

        detected, wake_word, remainder = self._detect_wake_word(raw)
        if not detected:
            self.rejected_count += 1
            return TranscriptDecision(False, "", "missing_wake_word")

        self.last_wake_word = wake_word
        self.last_wake_time = timestamp
        self.continue_listening(now=timestamp)
        if len(remainder) < self.min_post_wake_chars:
            self.rejected_count += 1
            self.false_positive_count += 1
            return TranscriptDecision(False, "", "wake_word_only", "Yes?")

        self.accepted_count += 1
        return TranscriptDecision(True, remainder, "accepted_wake_word")

    def confirmation_intent(self, text: str) -> str | None:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        if not normalized:
            return None
        if normalized in _CONFIRM_WORDS:
            return "confirm"
        if normalized in _DENY_WORDS:
            return "deny"
        if normalized in _REPEAT_WORDS:
            return "repeat"
        return None

    def status(self, *, now: float | None = None) -> dict[str, Any]:
        timestamp = time.monotonic() if now is None else float(now)
        followup_remaining = max(0.0, self.followup_until - timestamp)
        return {
            "mode": self.mode,
            "wake_words": list(self._wake_words),
            "wake_word_sensitivity": self.wake_word_sensitivity,
            "sleeping": self.sleeping,
            "followup_active": followup_remaining > 0.0,
            "followup_remaining_sec": followup_remaining,
            "timeout_profile": self.timeout_profile,
            "silence_timeout_sec": self.silence_timeout(),
            "barge_in_threshold": self.barge_in_threshold(),
            "push_to_talk_active": self.push_to_talk_active,
            "active_room": self.active_room,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "false_positive_count": self.false_positive_count,
            "last_wake_word": self.last_wake_word,
            "last_wake_time": self.last_wake_time,
        }
