"""Runtime constants for the Jarvis application loop."""

from __future__ import annotations

import re

from jarvis.presence import State
from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES, TOOL_STORAGE_ERROR_DETAILS

# Audio constants
SILENCE_TIMEOUT = 0.8
MIN_UTTERANCE = 0.3
TURN_TAKING_THRESHOLD = 0.55
TURN_TAKING_BARGE_IN_THRESHOLD = 0.4
ATTENTION_RECENCY_SEC = 1.0
THINKING_FILLER_DELAY = 0.35
THINKING_FILLER_TEXT = "One moment."
TTS_TARGET_RMS = 0.08
TTS_GAIN_SMOOTH = 0.2
TTS_SENTENCE_PAUSE_SEC = 0.12
TTS_CONFIDENCE_PAUSE_SEC = 0.18
TTS_LOW_CONFIDENCE_WORDS = {"maybe", "probably", "might", "not sure", "uncertain", "i think", "i believe"}
INTENDED_QUERY_MIN_ATTENTION = 0.35
CONFIRMATION_PHRASE = "Did you mean me?"
REPAIR_CONFIRMATION_TEMPLATE = 'I may have misheard you as: "{text}". Say confirm to proceed, or repeat your request.'
REPAIR_REPEAT_PROMPT = "Understood. Please repeat your request."
REPAIR_CONFIDENCE_THRESHOLD = 0.45
REPAIR_MIN_WORDS = 2
AFFIRMATIONS = {"yes", "yeah", "yep", "yup", "correct", "affirmative", "sure", "please"}
NEGATIONS = {"no", "nope", "nah", "negative"}
TELEMETRY_LOG_EVERY_TURNS = 5
TELEMETRY_STORAGE_ERROR_DETAILS = TOOL_STORAGE_ERROR_DETAILS
TELEMETRY_SERVICE_ERROR_DETAILS = TOOL_SERVICE_ERROR_CODES - TELEMETRY_STORAGE_ERROR_DETAILS
WATCHDOG_POLL_SEC = 0.05
CONVERSATION_TRACE_MAXLEN = 200
EPISODIC_TIMELINE_MAXLEN = 200
VALID_PERSONA_STYLES = {"terse", "composed", "friendly", "jarvis"}
VALID_BACKCHANNEL_STYLES = {"quiet", "balanced", "expressive"}
VALID_VOICE_PROFILE_VERBOSITY = {"brief", "normal", "detailed"}
VALID_VOICE_PROFILE_CONFIRMATIONS = {"minimal", "standard", "strict"}
VALID_VOICE_PROFILE_PACE = {"slow", "normal", "fast"}
VALID_VOICE_PROFILE_TONE = {"auto", "formal", "witty", "empathetic", "direct"}
VALID_CONTROL_PRESETS = {"quiet_hours", "demo_mode", "maintenance_mode"}
VALID_OPERATOR_AUTH_MODES = {"off", "token", "session"}

MEMORY_FORGET_RE = re.compile(
    r"^(?:please\s+)?(?:forget|delete|remove)\s+(?:memory\s*)?(?:id\s*)?(?P<memory_id>\d+)\s*$",
    re.IGNORECASE,
)
MEMORY_UPDATE_RE = re.compile(
    r"^(?:please\s+)?(?:update|change|edit)\s+(?:memory\s*)?(?:id\s*)?(?P<memory_id>\d+)\s+(?:to|with)\s+(?P<text>.+)$",
    re.IGNORECASE,
)
ACTION_INTENT_TERMS = {
    "turn",
    "set",
    "open",
    "close",
    "lock",
    "unlock",
    "arm",
    "disarm",
    "play",
    "pause",
    "send",
    "notify",
    "remind",
    "create",
    "update",
    "delete",
    "forget",
    "add",
    "trigger",
}
QUESTION_START_TERMS = {"what", "when", "where", "who", "why", "how", "is", "are", "can", "could", "would", "should"}
CORRECTION_TERMS = {
    "actually",
    "i meant",
    "correction",
    "that's wrong",
    "that is wrong",
    "not that",
    "instead",
    "rather",
    "change that",
}
FOLLOWUP_CARRYOVER_MAX_AGE_SEC = 120.0
FOLLOWUP_CARRYOVER_PREFIX_TERMS = (
    "and ",
    "also ",
    "then ",
    "what about",
    "how about",
    "plus ",
    "as well",
    "same for",
)
FOLLOWUP_CARRYOVER_REFERENCE_TERMS = {"it", "that", "this", "them", "there", "one", "same"}
FOLLOWUP_CARRYOVER_SHORT_REPLY_MAX_WORDS = 8
FOLLOWUP_CARRYOVER_ACK_TERMS = {"yes", "yep", "yeah", "no", "nope", "ok", "okay", "thanks", "thank", "sure"}
RUNTIME_INVARIANT_HISTORY_MAXLEN = 40
TURN_CHOREOGRAPHY_CUES: dict[State, dict[str, float | str]] = {
    State.IDLE: {"label": "idle_reset", "turn_lean": 0.0, "turn_tilt": 0.0, "turn_glance_yaw": 0.0},
    State.LISTENING: {"label": "listen_lean_in", "turn_lean": 1.5, "turn_tilt": -1.0, "turn_glance_yaw": -3.0},
    State.THINKING: {"label": "think_glance_away", "turn_lean": 0.5, "turn_tilt": 2.0, "turn_glance_yaw": 8.0},
    State.SPEAKING: {"label": "answer_lock_on", "turn_lean": 1.0, "turn_tilt": 0.0, "turn_glance_yaw": 0.0},
    State.MUTED: {"label": "muted_privacy", "turn_lean": 0.0, "turn_tilt": 0.0, "turn_glance_yaw": 0.0},
}
