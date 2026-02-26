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

SYSTEM_PROMPT = """\
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

STYLE_INSTRUCTIONS = {
    "terse": "Keep responses extremely brief and direct. Default to one sentence unless detail is explicitly requested.",
    "composed": "Use calm, precise phrasing with concise structure and restrained wit.",
    "friendly": "Use warm, approachable phrasing while keeping answers short and practical.",
}


class Brain:
    """Manages conversation with Claude using ClaudeSDKClient for multi-turn."""

    def __init__(self, config: Config, presence: PresenceLoop):
        self._config = config
        self._presence = presence
        self._session_id = "jarvis"
        self._memory = MemoryStore(config.memory_path) if config.memory_enabled else None

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
                "mcp__jarvis-services__todoist_add_task",
                "mcp__jarvis-services__todoist_list_tasks",
                "mcp__jarvis-services__pushover_notify",
                "mcp__jarvis-services__get_time",
                "mcp__jarvis-services__system_status",
                "mcp__jarvis-services__system_status_contract",
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

        style_instruction = self._style_instruction_context()
        if style_instruction:
            user_text = f"{user_text}\n\nPrompt style:\n{style_instruction}"

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
