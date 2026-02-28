from __future__ import annotations

import math
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


VALID_WAKE_MODES = {"always_listening", "wake_word", "push_to_talk"}
VALID_TIMEOUT_PROFILES = {"short", "normal", "long"}
WAKE_CALIBRATION_PROFILES: dict[str, dict[str, float | int]] = {
    "default": {
        "wake_word_sensitivity": 0.82,
        "followup_window_scale": 1.0,
        "min_post_wake_chars": 4,
        "false_trigger_threshold": 3,
        "false_trigger_window_sec": 30.0,
        "suppression_cooldown_sec": 8.0,
        "dynamic_sensitivity_boost": 0.05,
    },
    "quiet_room": {
        "wake_word_sensitivity": 0.78,
        "followup_window_scale": 1.1,
        "min_post_wake_chars": 3,
        "false_trigger_threshold": 4,
        "false_trigger_window_sec": 25.0,
        "suppression_cooldown_sec": 6.0,
        "dynamic_sensitivity_boost": 0.03,
    },
    "noisy_room": {
        "wake_word_sensitivity": 0.90,
        "followup_window_scale": 0.9,
        "min_post_wake_chars": 6,
        "false_trigger_threshold": 2,
        "false_trigger_window_sec": 35.0,
        "suppression_cooldown_sec": 12.0,
        "dynamic_sensitivity_boost": 0.08,
    },
    "tv_room": {
        "wake_word_sensitivity": 0.92,
        "followup_window_scale": 0.85,
        "min_post_wake_chars": 7,
        "false_trigger_threshold": 2,
        "false_trigger_window_sec": 40.0,
        "suppression_cooldown_sec": 15.0,
        "dynamic_sensitivity_boost": 0.10,
    },
    "far_field": {
        "wake_word_sensitivity": 0.86,
        "followup_window_scale": 1.0,
        "min_post_wake_chars": 5,
        "false_trigger_threshold": 3,
        "false_trigger_window_sec": 35.0,
        "suppression_cooldown_sec": 10.0,
        "dynamic_sensitivity_boost": 0.07,
    },
}

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


def _compact_whitespace(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _word_tokens(text: str) -> list[str]:
    chars: list[str] = []
    for ch in str(text or ""):
        chars.append(ch if (ch.isalnum() or ch == "'") else " ")
    return [token for token in "".join(chars).split() if token]


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
    wake_calibration_profile: str = "default"
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
        self._base_wake_word_sensitivity = self._normalize_sensitivity(config.wake_word_sensitivity)
        self.wake_word_sensitivity = self._base_wake_word_sensitivity
        self._base_followup_window_sec = max(0.0, float(config.followup_window_sec))
        self.followup_window_sec = self._base_followup_window_sec
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
        self._base_min_post_wake_chars = max(1, int(config.min_post_wake_chars))
        self.min_post_wake_chars = self._base_min_post_wake_chars
        self.calibration_profile = "default"
        self.false_trigger_threshold = 3
        self.false_trigger_window_sec = 30.0
        self.suppression_cooldown_sec = 8.0
        self.dynamic_sensitivity_boost = 0.05
        self.active_room = (config.room_default or "main").strip().lower() or "main"

        self.push_to_talk_active = False
        self.sleeping = False
        self.followup_until = 0.0
        self._wake_suppressed_until = 0.0
        self._wake_false_trigger_times: list[float] = []
        self.last_wake_word = ""
        self.last_wake_time = 0.0

        self.accepted_count = 0
        self.rejected_count = 0
        self.false_positive_count = 0
        self._speech_rate_wps = 2.5
        self._interruption_likelihood = 0.0
        self.set_calibration_profile(config.wake_calibration_profile)

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        candidate = (mode or "always_listening").strip().lower()
        return candidate if candidate in VALID_WAKE_MODES else "always_listening"

    @staticmethod
    def _normalize_calibration_profile(profile: str) -> str:
        candidate = (profile or "default").strip().lower()
        return candidate if candidate in WAKE_CALIBRATION_PROFILES else "default"

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

    def set_calibration_profile(self, profile: str) -> str:
        selected = self._normalize_calibration_profile(profile)
        settings = WAKE_CALIBRATION_PROFILES.get(selected, WAKE_CALIBRATION_PROFILES["default"])
        self.calibration_profile = selected
        sensitivity = float(settings.get("wake_word_sensitivity", self._base_wake_word_sensitivity))
        self.wake_word_sensitivity = self._normalize_sensitivity(max(self._base_wake_word_sensitivity, sensitivity))
        followup_scale = float(settings.get("followup_window_scale", 1.0))
        if not math.isfinite(followup_scale):
            followup_scale = 1.0
        followup_scale = max(0.5, min(1.5, followup_scale))
        self.followup_window_sec = max(0.5, self._base_followup_window_sec * followup_scale)
        min_chars = int(settings.get("min_post_wake_chars", self._base_min_post_wake_chars))
        self.min_post_wake_chars = max(self._base_min_post_wake_chars, min_chars)
        threshold = int(settings.get("false_trigger_threshold", self.false_trigger_threshold))
        self.false_trigger_threshold = max(1, threshold)
        window_sec = float(settings.get("false_trigger_window_sec", self.false_trigger_window_sec))
        self.false_trigger_window_sec = max(1.0, window_sec if math.isfinite(window_sec) else self.false_trigger_window_sec)
        cooldown_sec = float(settings.get("suppression_cooldown_sec", self.suppression_cooldown_sec))
        self.suppression_cooldown_sec = max(1.0, cooldown_sec if math.isfinite(cooldown_sec) else self.suppression_cooldown_sec)
        boost = float(settings.get("dynamic_sensitivity_boost", self.dynamic_sensitivity_boost))
        self.dynamic_sensitivity_boost = max(0.0, min(0.2, boost if math.isfinite(boost) else self.dynamic_sensitivity_boost))
        return self.calibration_profile

    def set_timeout_profile(self, profile: str) -> str:
        self.timeout_profile = self._normalize_timeout_profile(profile)
        return self.timeout_profile

    def set_push_to_talk_active(self, active: bool) -> None:
        self.push_to_talk_active = bool(active)

    def _prune_false_trigger_history(self, now: float) -> None:
        cutoff = now - self.false_trigger_window_sec
        self._wake_false_trigger_times = [ts for ts in self._wake_false_trigger_times if ts >= cutoff]

    def _register_false_trigger(self, now: float) -> bool:
        self._wake_false_trigger_times.append(now)
        self._prune_false_trigger_history(now)
        if len(self._wake_false_trigger_times) < self.false_trigger_threshold:
            return False
        self._wake_suppressed_until = max(self._wake_suppressed_until, now + self.suppression_cooldown_sec)
        return True

    def _effective_wake_sensitivity(self, now: float) -> float:
        self._prune_false_trigger_history(now)
        if not self._wake_false_trigger_times:
            return self.wake_word_sensitivity
        load = min(1.0, len(self._wake_false_trigger_times) / max(1, self.false_trigger_threshold))
        boosted = self.wake_word_sensitivity + (self.dynamic_sensitivity_boost * load)
        return self._normalize_sensitivity(boosted)

    def _compute_adaptive_timeout(self) -> float:
        base = float(self.timeout_profiles.get(self.timeout_profile, self.timeout_profiles["normal"]))
        speech_rate = max(0.0, float(self._speech_rate_wps))
        interruption = max(0.0, min(1.0, float(self._interruption_likelihood)))
        # Slow speakers need a wider pause window to avoid clipped utterances.
        slow_boost = max(0.0, min(0.4, (2.2 - speech_rate) * 0.18))
        # Fast speakers and interruption-heavy contexts benefit from shorter turn-closing latency.
        fast_reduction = max(0.0, min(0.25, (speech_rate - 3.8) * 0.08))
        interruption_reduction = interruption * 0.2
        scale = 1.0 + slow_boost - fast_reduction - interruption_reduction
        adaptive = base * scale
        return max(0.2, min(2.5, adaptive))

    def silence_timeout(self) -> float:
        return self._compute_adaptive_timeout()

    def barge_in_threshold(self) -> float:
        return float(self.barge_thresholds.get(self.mode, 0.4))

    def continue_listening(self, *, now: float | None = None, window_sec: float | None = None) -> None:
        base = time.monotonic() if now is None else float(now)
        window = self.followup_window_sec if window_sec is None else max(0.0, float(window_sec))
        self.followup_until = base + window

    def register_utterance(
        self,
        text: str,
        *,
        duration_sec: float,
        interruption_likelihood: float | None = None,
    ) -> None:
        try:
            duration = float(duration_sec)
        except (TypeError, ValueError):
            duration = 0.0
        duration = max(0.1, duration)
        words = _word_tokens(text)
        if words:
            rate = len(words) / duration
            if math.isfinite(rate):
                self._speech_rate_wps = (self._speech_rate_wps * 0.7) + (rate * 0.3)
        if interruption_likelihood is not None:
            try:
                parsed_interrupt = float(interruption_likelihood)
            except (TypeError, ValueError):
                parsed_interrupt = 0.0
            if not math.isfinite(parsed_interrupt):
                parsed_interrupt = 0.0
            self._interruption_likelihood = max(0.0, min(1.0, parsed_interrupt))

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

    def _detect_wake_word(self, text: str, *, sensitivity: float | None = None) -> tuple[bool, str, str]:
        compact = _compact_whitespace(text)
        if not compact:
            return False, "", ""
        threshold = self.wake_word_sensitivity if sensitivity is None else self._normalize_sensitivity(sensitivity)
        for wake_word in self._wake_words:
            wake_compact = _compact_whitespace(wake_word)
            prefix = compact[: len(wake_compact)]
            if self._similarity(prefix, wake_compact) >= threshold:
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
            if timestamp < self._wake_suppressed_until:
                self.rejected_count += 1
                return TranscriptDecision(False, "", "suppressed_false_trigger_window")
            sensitivity = self._effective_wake_sensitivity(timestamp)
            detected, wake_word, remainder = self._detect_wake_word(raw, sensitivity=sensitivity)
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
                suppressed = self._register_false_trigger(timestamp)
                reason = "wake_word_only_suppressed" if suppressed else "wake_word_only"
                reply = "Please repeat with your request." if suppressed else "Yes?"
                return TranscriptDecision(False, "", reason, reply)
            self.accepted_count += 1
            return TranscriptDecision(True, remainder, "accepted_wake_word")

        if timestamp < self.followup_until:
            self.accepted_count += 1
            self.continue_listening(now=timestamp)
            return TranscriptDecision(True, raw, "accepted_followup")

        if timestamp < self._wake_suppressed_until:
            self.rejected_count += 1
            return TranscriptDecision(False, "", "suppressed_false_trigger_window")
        sensitivity = self._effective_wake_sensitivity(timestamp)
        detected, wake_word, remainder = self._detect_wake_word(raw, sensitivity=sensitivity)
        if not detected:
            self.rejected_count += 1
            return TranscriptDecision(False, "", "missing_wake_word")

        self.last_wake_word = wake_word
        self.last_wake_time = timestamp
        self.continue_listening(now=timestamp)
        if len(remainder) < self.min_post_wake_chars:
            self.rejected_count += 1
            self.false_positive_count += 1
            suppressed = self._register_false_trigger(timestamp)
            reason = "wake_word_only_suppressed" if suppressed else "wake_word_only"
            reply = "Please repeat with your request." if suppressed else "Yes?"
            return TranscriptDecision(False, "", reason, reply)

        self.accepted_count += 1
        return TranscriptDecision(True, remainder, "accepted_wake_word")

    def confirmation_intent(self, text: str) -> str | None:
        normalized = _compact_whitespace(text)
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
        suppression_remaining = max(0.0, self._wake_suppressed_until - timestamp)
        return {
            "mode": self.mode,
            "wake_words": list(self._wake_words),
            "wake_calibration_profile": self.calibration_profile,
            "wake_word_sensitivity": self.wake_word_sensitivity,
            "effective_wake_word_sensitivity": self._effective_wake_sensitivity(timestamp),
            "sleeping": self.sleeping,
            "followup_active": followup_remaining > 0.0,
            "followup_remaining_sec": followup_remaining,
            "wake_suppressed": suppression_remaining > 0.0,
            "wake_suppressed_remaining_sec": suppression_remaining,
            "false_trigger_threshold": self.false_trigger_threshold,
            "false_trigger_window_sec": self.false_trigger_window_sec,
            "timeout_profile": self.timeout_profile,
            "silence_timeout_sec": self.silence_timeout(),
            "adaptive_silence_timeout_sec": self.silence_timeout(),
            "speech_rate_wps": self._speech_rate_wps,
            "interruption_likelihood": self._interruption_likelihood,
            "barge_in_threshold": self.barge_in_threshold(),
            "push_to_talk_active": self.push_to_talk_active,
            "active_room": self.active_room,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "false_positive_count": self.false_positive_count,
            "last_wake_word": self.last_wake_word,
            "last_wake_time": self.last_wake_time,
        }
