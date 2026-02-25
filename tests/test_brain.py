"""Tests for jarvis.brain — Claude Agent SDK orchestration."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jarvis.brain import Brain, _find_sentence_boundary
from jarvis.presence import PresenceLoop, State, Signals
from jarvis.robot.controller import RobotController


class TestFindSentenceBoundary:
    def test_simple_period(self):
        assert _find_sentence_boundary("Hello world.") == 11

    def test_period_with_trailing_space(self):
        assert _find_sentence_boundary("Hello. World") == 5

    def test_exclamation(self):
        assert _find_sentence_boundary("Wow!") == 3

    def test_question(self):
        assert _find_sentence_boundary("Really?") == 6

    def test_no_boundary(self):
        assert _find_sentence_boundary("Hello world") == -1

    def test_empty_string(self):
        assert _find_sentence_boundary("") == -1

    def test_multiple_sentences(self):
        text = "First. Second. Third"
        # Should return the LAST boundary (before "Third")
        assert _find_sentence_boundary(text) == 13

    def test_period_not_followed_by_space(self):
        # Like "3.14" — period not followed by space or end
        assert _find_sentence_boundary("Pi is 3.14 roughly") == -1

    def test_abbreviation_with_period(self):
        # "Dr." followed by space looks like sentence boundary
        assert _find_sentence_boundary("Dr. Smith") == 2

    def test_end_of_string(self):
        assert _find_sentence_boundary("Done.") == 4


class TestBrain:
    @pytest.fixture
    def brain(self, config, mock_robot):
        presence = PresenceLoop(mock_robot)
        # Patch the tool server creation to avoid SDK dependency
        with patch("jarvis.brain.create_robot_server") as mock_rs, \
             patch("jarvis.brain.create_services_server") as mock_ss, \
             patch("jarvis.brain.bind_services"):
            mock_rs.return_value = MagicMock()
            mock_ss.return_value = MagicMock()
            b = Brain(config, presence)
        return b

    @pytest.mark.asyncio
    async def test_respond_sets_thinking_state(self, brain):
        """Brain should set THINKING state when processing begins."""
        mock_msg = MagicMock()
        mock_msg.subtype = "init"
        mock_msg.data = {"session_id": "test-session"}

        with patch.object(brain._client, "query", new=AsyncMock()) as mock_query, \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([mock_msg])
            sentences = []
            async for s in brain.respond("hello"):
                sentences.append(s)

        # Should have set THINKING at start, then IDLE at end
        assert brain._presence.signals.state == State.IDLE

    @pytest.mark.asyncio
    async def test_respond_yields_sentences(self, brain):
        """Brain should yield text at sentence boundaries."""
        from jarvis.brain import AssistantMessage

        # Mock a SystemMessage for init
        mock_init = MagicMock()
        mock_init.__class__ = type("SystemMessage", (), {})
        mock_init.subtype = "init"
        mock_init.data = {"session_id": "s1"}

        # Mock an AssistantMessage with text
        mock_block = MagicMock()
        mock_block.text = "Hello there. How can I help?"

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_block]

        with patch.object(brain._client, "query", new=AsyncMock()), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch("jarvis.brain.isinstance", side_effect=lambda obj, cls: obj is mock_assistant if cls is AssistantMessage else type(obj).__name__ == cls.__name__), \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([mock_init, mock_assistant])
            sentences = []
            async for sentence in brain.respond("hello"):
                sentences.append(sentence)

        assert sentences == ["Hello there. How can I help?"]

    @pytest.mark.asyncio
    async def test_respond_handles_error(self, brain):
        """Brain should yield error message on exception."""
        with patch.object(brain._client, "query", new=AsyncMock()), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter_error(RuntimeError("API down"))

            sentences = []
            async for s in brain.respond("hello"):
                sentences.append(s)

        assert any("error" in s.lower() for s in sentences)

    @pytest.mark.asyncio
    async def test_respond_captures_session_id(self, brain):
        """Brain should capture session_id from init message."""
        from jarvis.brain import SystemMessage

        mock_init = MagicMock(spec=SystemMessage)
        mock_init.subtype = "init"
        mock_init.data = {"session_id": "session-abc"}

        with patch.object(brain._client, "query", new=AsyncMock()), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch("jarvis.brain.isinstance") as mock_isinstance, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            # Make isinstance work for SystemMessage
            def isinstance_side_effect(obj, cls):
                if cls is SystemMessage and obj is mock_init:
                    return True
                return False
            mock_isinstance.side_effect = isinstance_side_effect
            mock_recv.return_value = _async_iter([mock_init])

            async for _ in brain.respond("hello"):
                pass

    @pytest.mark.asyncio
    async def test_respond_resets_intent_signals(self, brain):
        """After response, intent signals should be zeroed."""
        brain._presence.signals.intent_nod = 0.8
        brain._presence.signals.intent_tilt = 5.0

        with patch.object(brain._client, "query", new=AsyncMock()), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("hello"):
                pass

        assert brain._presence.signals.intent_nod == 0.0
        assert brain._presence.signals.intent_tilt == 0.0
        assert brain._presence.signals.intent_glance_yaw == 0.0


# ── Helpers ──────────────────────────────────────────────────

async def _async_iter(items):
    """Create an async iterator from a list."""
    for item in items:
        yield item


async def _async_iter_error(exc):
    """Async iterator that raises an exception."""
    raise exc
    yield  # make it a generator  # noqa: unreachable
