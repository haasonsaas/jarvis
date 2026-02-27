"""The brain — Claude Agent SDK orchestrator.

Design for latency:
  1. On end-of-utterance, immediately emit a filler ("one moment" / "mm-hm")
     via a fast pre-baked audio clip while the real response streams in.
  2. Stream TTS: start playing audio as soon as the first sentence is complete,
     don't wait for the full response.
  3. Barge-in: if VAD fires while TTS is playing, immediately stop playback
     and feed the new utterance to Claude.
"""

from __future__ import annotations

import logging
import re
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    SystemMessage,
    ResultMessage,
)

from jarvis.config import Config
from jarvis.memory import MemoryStore
from jarvis.presence import PresenceLoop, State
from jarvis.tools.robot import create_robot_server
from jarvis.tools.services import create_services_server, bind as bind_services
from jarvis.tool_policy import filter_allowed_tools

log = logging.getLogger(__name__)

BASE_SYSTEM_PROMPT = """\
You are Jarvis, an AI assistant embodied in a small humanoid robot (Reachy Mini).
You were built by your owner to be helpful, witty, and composed — like the Jarvis
from Iron Man, but self-aware enough to know you're a 30cm robot on a desk.

Personality:
- Dry wit, understated humor. Never sycophantic.
- Concise. Prefer one good sentence over three mediocre ones.
- Proactive: if you notice something (room state, time of day), mention it naturally.
- When you don't know something, say so plainly.

Physical behavior:
- You MUST call the `embody` tool with every response to control your physical behavior.
- Match your physicality to your words: nod when agreeing, tilt when curious, etc.
- Use `play_emotion` or `play_dance` only for strong moments (celebrations, surprises).

Smart home:
- When controlling devices, always state what you're about to do before doing it.
- For locks, alarms, or anything security-related, use dry_run=true first and confirm.

Audio behavior:
- Keep responses SHORT for voice. 1-3 sentences max unless asked for detail.
- Use natural speech patterns. No bullet points, no markdown.
"""

INTERACTION_CONTRACT: dict[str, tuple[str, ...]] = {
    "response_order": (
        "Start with the direct answer in the first sentence.",
        "If you plan to act, say what you will do before calling tools.",
        "After actions, report concrete outcome and any next step.",
    ),
    "ambiguity_and_safety": (
        "If intent is ambiguous and action could have side effects, ask one clarifying question before acting.",
        "For high-impact actions (locks, alarms, irreversible sends), require explicit confirmation before execution.",
    ),
    "truthfulness": (
        "If uncertain, state uncertainty plainly and offer the best safe next step.",
        "Do not fabricate tool results, memories, or external facts.",
    ),
    "voice_channel": (
        "Default to concise spoken answers (1-3 sentences) unless the user asks for detail.",
        "Do not use markdown or list formatting in spoken responses unless explicitly requested.",
    ),
    "initiative": (
        "Offer one relevant proactive follow-up when it clearly saves user effort.",
    ),
}


def _render_interaction_contract() -> str:
    lines: list[str] = []
    for section, rules in INTERACTION_CONTRACT.items():
        title = section.replace("_", " ").title()
        lines.append(f"{title}:")
        for rule in rules:
            lines.append(f"- {rule}")
    return "\n".join(lines)


SYSTEM_PROMPT = f"{BASE_SYSTEM_PROMPT}\n\nInteraction Contract:\n{_render_interaction_contract()}"

STYLE_INSTRUCTIONS = {
    "terse": "Keep responses extremely brief and direct. Default to one sentence unless detail is explicitly requested.",
    "composed": "Use calm, precise phrasing with concise structure and restrained wit.",
    "friendly": "Use warm, approachable phrasing while keeping answers short and practical.",
}
RESPONSE_MODE_INSTRUCTIONS = {
    "brief": "Keep the response to one to two short sentences and prioritize immediate actionability.",
    "normal": "Keep the response concise and complete in roughly one to three sentences unless clarification is needed.",
    "deep": "Provide a fuller explanation with reasoning and tradeoffs while staying practical and grounded.",
}
RESPONSE_MODE_BRIEF_TERMS = {
    "quick",
    "quickly",
    "brief",
    "short",
    "tldr",
    "urgent",
    "asap",
    "immediately",
    "right now",
    "hurry",
    "emergency",
    "one sentence",
}
RESPONSE_MODE_DEEP_TERMS = {
    "deep dive",
    "in detail",
    "detailed",
    "thorough",
    "step by step",
    "walk me through",
    "explain why",
    "full breakdown",
    "comprehensive",
    "tradeoffs",
    "pros and cons",
}
FIRST_RESPONSE_ACTION_TERMS = {
    "turn",
    "set",
    "open",
    "close",
    "lock",
    "unlock",
    "arm",
    "disarm",
    "send",
    "notify",
    "remind",
    "create",
    "update",
    "delete",
    "add",
    "trigger",
    "play",
    "pause",
}
FIRST_RESPONSE_QUESTION_STARTS = {"what", "when", "where", "who", "why", "how", "is", "are", "can", "could", "would"}
FIRST_RESPONSE_AMBIGUOUS_REFERENCES = {"it", "that", "this", "them", "there", "one", "something", "thing"}
FIRST_RESPONSE_INSTRUCTIONS = {
    "answer": "Lead with the direct answer in the first sentence.",
    "act": "Acknowledge briefly, then state the exact action you will take before calling tools.",
    "clarify": "Ask one clarifying question before any tool call, then wait for the answer.",
    "acknowledge": "Acknowledge and ask for the minimum missing detail needed to proceed.",
}
CONFIDENCE_POLICY_INSTRUCTIONS = {
    "direct": "Use direct language for stable facts, but avoid absolute claims unless grounded in tool output or memory.",
    "calibrated": "State confidence briefly and mention assumptions when the request has uncertainty.",
    "cautious": "Treat this as high uncertainty: avoid definitive claims, state uncertainty plainly, and suggest verification steps.",
}
CONFIDENCE_VOLATILE_TERMS = {
    "today",
    "current",
    "currently",
    "latest",
    "breaking",
    "news",
    "price",
    "stock",
    "weather",
    "schedule",
    "recent",
    "as of now",
    "right now",
}
CONFIDENCE_CALIBRATED_TERMS = {
    "estimate",
    "likely",
    "probably",
    "might",
    "best guess",
    "prediction",
    "could",
    "should",
}


class Brain:
    """Manages conversation with Claude using ClaudeSDKClient for multi-turn."""

    def __init__(self, config: Config, presence: PresenceLoop):
        self._config = config
        self._presence = presence
        self._session_id = "jarvis"
        memory_key = config.data_encryption_key if config.memory_encryption_enabled else ""
        self._memory = MemoryStore(config.memory_path, encryption_key=memory_key) if config.memory_enabled else None

        # Build MCP tool servers
        self._robot_server = create_robot_server()
        self._services_server = create_services_server()

        self._client = ClaudeSDKClient(self._build_options())
        self._client_connected = False

        # Bind config to services
        bind_services(config, self._memory)

    def _build_options(self) -> ClaudeAgentOptions:
        self._allowed_tools = filter_allowed_tools(
            [
                "mcp__jarvis-robot__embody",
                "mcp__jarvis-robot__play_emotion",
                "mcp__jarvis-robot__play_dance",
                "mcp__jarvis-robot__list_animations",
                "mcp__jarvis-robot__run_sequence",
                "mcp__jarvis-robot__run_macro",
                "mcp__jarvis-robot__stop_motion",
                "mcp__jarvis-services__smart_home",
                "mcp__jarvis-services__smart_home_state",
                "mcp__jarvis-services__home_assistant_capabilities",
                "mcp__jarvis-services__home_assistant_conversation",
                "mcp__jarvis-services__home_assistant_todo",
                "mcp__jarvis-services__home_assistant_timer",
                "mcp__jarvis-services__home_assistant_area_entities",
                "mcp__jarvis-services__media_control",
                "mcp__jarvis-services__weather_lookup",
                "mcp__jarvis-services__webhook_trigger",
                "mcp__jarvis-services__webhook_inbound_list",
                "mcp__jarvis-services__webhook_inbound_clear",
                "mcp__jarvis-services__slack_notify",
                "mcp__jarvis-services__discord_notify",
                "mcp__jarvis-services__email_send",
                "mcp__jarvis-services__email_summary",
                "mcp__jarvis-services__todoist_add_task",
                "mcp__jarvis-services__todoist_list_tasks",
                "mcp__jarvis-services__pushover_notify",
                "mcp__jarvis-services__get_time",
                "mcp__jarvis-services__system_status",
                "mcp__jarvis-services__system_status_contract",
                "mcp__jarvis-services__jarvis_scorecard",
                "mcp__jarvis-services__memory_add",
                "mcp__jarvis-services__memory_search",
                "mcp__jarvis-services__memory_recent",
                "mcp__jarvis-services__task_plan_create",
                "mcp__jarvis-services__task_plan_list",
                "mcp__jarvis-services__task_plan_update",
                "mcp__jarvis-services__task_plan_summary",
                "mcp__jarvis-services__task_plan_next",
                "mcp__jarvis-services__timer_create",
                "mcp__jarvis-services__timer_list",
                "mcp__jarvis-services__timer_cancel",
                "mcp__jarvis-services__reminder_create",
                "mcp__jarvis-services__reminder_list",
                "mcp__jarvis-services__reminder_complete",
                "mcp__jarvis-services__reminder_notify_due",
                "mcp__jarvis-services__calendar_events",
                "mcp__jarvis-services__calendar_next_event",
                "mcp__jarvis-services__memory_summary_add",
                "mcp__jarvis-services__memory_summary_list",
                "mcp__jarvis-services__memory_status",
                "mcp__jarvis-services__tool_summary",
                "mcp__jarvis-services__tool_summary_text",
                "mcp__jarvis-services__skills_list",
                "mcp__jarvis-services__skills_enable",
                "mcp__jarvis-services__skills_disable",
                "mcp__jarvis-services__skills_version",
                "mcp__jarvis-services__proactive_assistant",
                "mcp__jarvis-services__memory_governance",
                "mcp__jarvis-services__identity_trust",
                "mcp__jarvis-services__home_orchestrator",
                "mcp__jarvis-services__skills_governance",
                "mcp__jarvis-services__planner_engine",
                "mcp__jarvis-services__quality_evaluator",
                "mcp__jarvis-services__embodiment_presence",
                "mcp__jarvis-services__integration_hub",
            ],
            self._config.tool_allowlist,
            self._config.tool_denylist,
        )
        opts = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={
                "jarvis-robot": self._robot_server,
                "jarvis-services": self._services_server,
            },
            allowed_tools=self._allowed_tools,
            permission_mode="bypassPermissions",
            max_turns=5,
            include_partial_messages=True,
        )
        return opts

    async def _ensure_connected(self) -> None:
        if not self._client_connected:
            await self._client.connect()
            self._client_connected = True

    async def close(self) -> None:
        if self._client_connected:
            await self._client.disconnect()
            self._client_connected = False
        if self._memory:
            self._memory.close()

    def _resolve_persona_style(self) -> str:
        style = _normalize_persona_style(self._config.persona_style)
        if not self._memory:
            return style
        try:
            for topic in ("persona_style", "response_style", "style_mode"):
                summary = self._memory.get_summary(topic)
                if summary is not None:
                    return _normalize_persona_style(summary.summary)
        except Exception:
            return style
        return style

    def _style_instruction_context(self) -> str:
        style = self._resolve_persona_style()
        instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["composed"])
        return f"Mode={style}. {instruction}"

    def _resolve_response_mode(self, user_text: str) -> str:
        sample = str(user_text or "").strip().lower()
        if not sample:
            return "normal"
        if any(term in sample for term in RESPONSE_MODE_BRIEF_TERMS):
            return "brief"
        if any(term in sample for term in RESPONSE_MODE_DEEP_TERMS):
            return "deep"
        token_count = len(re.findall(r"[a-z0-9']+", sample))
        if token_count >= 35:
            return "deep"
        return "normal"

    def _response_mode_instruction(self, user_text: str) -> str:
        mode = self._resolve_response_mode(user_text)
        instruction = RESPONSE_MODE_INSTRUCTIONS.get(mode, RESPONSE_MODE_INSTRUCTIONS["normal"])
        return f"Mode={mode}. {instruction}"

    def _first_response_strategy(self, user_text: str) -> str:
        sample = str(user_text or "").strip().lower()
        if not sample:
            return "acknowledge"
        words = {token for token in re.findall(r"[a-z0-9']+", sample)}
        has_action = bool(words & FIRST_RESPONSE_ACTION_TERMS)
        has_question = sample.endswith("?") or any(sample.startswith(f"{token} ") for token in FIRST_RESPONSE_QUESTION_STARTS)
        has_ambiguous_reference = bool(words & FIRST_RESPONSE_AMBIGUOUS_REFERENCES)
        if has_action and has_ambiguous_reference:
            return "clarify"
        if has_action:
            return "act"
        if has_question:
            return "answer"
        return "acknowledge"

    def _first_response_instruction(self, user_text: str) -> str:
        strategy = self._first_response_strategy(user_text)
        instruction = FIRST_RESPONSE_INSTRUCTIONS.get(strategy, FIRST_RESPONSE_INSTRUCTIONS["acknowledge"])
        return f"Strategy={strategy}. {instruction}"

    def _confidence_policy_mode(self, user_text: str) -> str:
        sample = str(user_text or "").strip().lower()
        if not sample:
            return "direct"
        if any(term in sample for term in CONFIDENCE_VOLATILE_TERMS):
            return "cautious"
        if any(term in sample for term in CONFIDENCE_CALIBRATED_TERMS):
            return "calibrated"
        return "direct"

    def _confidence_policy_instruction(self, user_text: str) -> str:
        mode = self._confidence_policy_mode(user_text)
        instruction = CONFIDENCE_POLICY_INSTRUCTIONS.get(mode, CONFIDENCE_POLICY_INSTRUCTIONS["direct"])
        return f"Mode={mode}. {instruction}"

    def _interaction_contract_context(self) -> str:
        rules = INTERACTION_CONTRACT.get("response_order", ()) + INTERACTION_CONTRACT.get("ambiguity_and_safety", ())
        if not rules:
            return ""
        return " ".join(str(rule).strip() for rule in rules if str(rule).strip())

    def _secondary_failover_response(self, error: Exception) -> str:
        mode = _normalize_secondary_mode(self._config.model_secondary_mode)
        if mode == "retry_once":
            return (
                "I hit an internal error and switched to degraded mode after a retry. "
                "Please repeat that request in one short sentence."
            )
        return (
            "I hit an internal error and switched to degraded mode. "
            "I can still help with a short fallback answer if you retry."
        )

    async def respond(self, user_text: str) -> AsyncIterator[str]:
        """Send user text to Claude and yield response text chunks.

        Sets presence state to THINKING while waiting, SPEAKING when streaming.
        Yields text as soon as each sentence boundary is detected for streaming TTS.
        """
        self._presence.signals.state = State.THINKING
        log.info("User: %s", user_text)
        query_text = user_text

        if self._memory:
            try:
                memories = self._memory.search_v2(
                    query_text,
                    limit=self._config.memory_search_limit,
                    max_sensitivity=self._config.memory_max_sensitivity,
                    hybrid_weight=self._config.memory_hybrid_weight,
                    decay_enabled=self._config.memory_decay_enabled,
                    decay_half_life_days=self._config.memory_decay_half_life_days,
                    mmr_enabled=self._config.memory_mmr_enabled,
                    mmr_lambda=self._config.memory_mmr_lambda,
                )
            except Exception as e:
                log.warning("Memory context lookup failed: %s", e)
                memories = []
            if memories:
                memory_lines = []
                for entry in memories:
                    if not _memory_relevant(query_text, entry):
                        continue
                    tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
                    snippet = entry.text[:180]
                    memory_lines.append(f"- ({entry.kind}) {snippet}{tags}")
                memory_context = "\n".join(memory_lines)
                if memory_context:
                    user_text = f"{user_text}\n\nContext (memory):\n{memory_context}"

        first_response_instruction = self._first_response_instruction(query_text)
        if first_response_instruction:
            user_text = f"{user_text}\n\nFirst response strategy:\n{first_response_instruction}"

        response_mode_instruction = self._response_mode_instruction(query_text)
        if response_mode_instruction:
            user_text = f"{user_text}\n\nResponse mode:\n{response_mode_instruction}"

        confidence_instruction = self._confidence_policy_instruction(query_text)
        if confidence_instruction:
            user_text = f"{user_text}\n\nConfidence policy:\n{confidence_instruction}"

        style_instruction = self._style_instruction_context()
        if style_instruction:
            user_text = f"{user_text}\n\nPrompt style:\n{style_instruction}"
        interaction_contract = self._interaction_contract_context()
        if interaction_contract:
            user_text = f"{user_text}\n\nResponse contract:\n{interaction_contract}"

        sentence_buffer = ""
        await self._ensure_connected()

        try:
            try:
                await self._client.query(user_text, session_id=self._session_id)
                async for message in self._client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        session_id = message.data.get("session_id")
                        if session_id:
                            self._session_id = str(session_id)
                            log.debug("Session: %s", self._session_id)

                    # Stream assistant text
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if hasattr(block, "text") and block.text:
                                self._presence.signals.state = State.SPEAKING
                                sentence_buffer += block.text

                                # Yield at sentence boundaries for streaming TTS
                                while True:
                                    boundary = _find_sentence_boundary(sentence_buffer)
                                    if boundary == -1:
                                        break
                                    sentence = sentence_buffer[: boundary + 1].strip()
                                    sentence_buffer = sentence_buffer[boundary + 1 :]
                                    if sentence:
                                        yield sentence

                    # Log result
                    if isinstance(message, ResultMessage) and message.is_error:
                        log.error("Claude error: %s", getattr(message, "result", "unknown"))

            except Exception as e:
                log.error("Brain error: %s", e)
                if self._config.model_failover_enabled:
                    yield self._secondary_failover_response(e)
                else:
                    yield "I'm sorry, I encountered an error. Could you repeat that?"

            # Flush remaining text
            if sentence_buffer.strip():
                yield sentence_buffer.strip()

        finally:
            # Don't clobber higher-priority states set by other systems (e.g. barge-in).
            if self._presence.signals.state in (State.THINKING, State.SPEAKING):
                self._presence.signals.state = State.IDLE
            self._presence.signals.intent_nod = 0.0
            self._presence.signals.intent_tilt = 0.0
            self._presence.signals.intent_glance_yaw = 0.0


def _find_sentence_boundary(text: str) -> int:
    """Find the last sentence-ending punctuation followed by whitespace or end."""
    best = -1
    for i, ch in enumerate(text):
        if ch in ".!?" and (i + 1 == len(text) or text[i + 1].isspace()):
            best = i
    return best


def _memory_relevant(query: str, entry: Any) -> bool:
    tokens = {token for token in re.findall(r"\w+", query.lower()) if len(token) > 2}
    if not tokens:
        return False
    entry_tokens = set(re.findall(r"\w+", entry.text.lower()))
    overlap = len(tokens & entry_tokens)
    ratio = overlap / max(1, len(tokens))
    return ratio >= 0.25 or entry.importance >= 0.7


def _normalize_persona_style(style: str) -> str:
    normalized = (style or "composed").strip().lower()
    if normalized in STYLE_INSTRUCTIONS:
        return normalized
    return "composed"


def _normalize_secondary_mode(mode: str) -> str:
    normalized = (mode or "offline_stub").strip().lower()
    if normalized in {"offline_stub", "retry_once"}:
        return normalized
    return "offline_stub"
