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

import asyncio
import logging
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    SystemMessage,
    ResultMessage,
)

from jarvis.config import Config
from jarvis.presence import PresenceLoop, State
from jarvis.tools.robot import create_robot_server, bind as bind_robot
from jarvis.tools.services import create_services_server, bind as bind_services

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


class Brain:
    """Manages conversation with Claude using ClaudeSDKClient for multi-turn."""

    def __init__(self, config: Config, presence: PresenceLoop):
        self._config = config
        self._presence = presence
        self._session_id: str | None = None

        # Build MCP tool servers
        self._robot_server = create_robot_server()
        self._services_server = create_services_server()

        # Bind config to services
        bind_services(config)

    def _build_options(self) -> ClaudeAgentOptions:
        opts = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={
                "jarvis-robot": self._robot_server,
                "jarvis-services": self._services_server,
            },
            allowed_tools=[
                "mcp__jarvis-robot__embody",
                "mcp__jarvis-robot__play_emotion",
                "mcp__jarvis-robot__play_dance",
                "mcp__jarvis-robot__list_animations",
                "mcp__jarvis-services__smart_home",
                "mcp__jarvis-services__smart_home_state",
            ],
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        if self._session_id:
            opts.resume = self._session_id
        return opts

    async def respond(self, user_text: str) -> AsyncIterator[str]:
        """Send user text to Claude and yield response text chunks.

        Sets presence state to THINKING while waiting, SPEAKING when streaming.
        Yields text as soon as each sentence boundary is detected for streaming TTS.
        """
        self._presence.signals.state = State.THINKING
        log.info("User: %s", user_text)

        sentence_buffer = ""

        try:
            try:
                async for message in query(
                    prompt=user_text,
                    options=self._build_options(),
                ):
                    # Capture session ID from init message
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        self._session_id = message.data.get("session_id")
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
    """Find the last sentence-ending punctuation followed by a space or end."""
    best = -1
    for i, ch in enumerate(text):
        if ch in ".!?" and (i + 1 == len(text) or text[i + 1] == " "):
            best = i
    return best
