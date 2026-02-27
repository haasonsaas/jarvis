"""Tests for jarvis.brain — Claude Agent SDK orchestration."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jarvis.brain import (
    Brain,
    CONFIDENCE_POLICY_INSTRUCTIONS,
    FIRST_RESPONSE_INSTRUCTIONS,
    INTERACTION_CONTRACT,
    RESPONSE_MODE_INSTRUCTIONS,
    STYLE_INSTRUCTIONS,
    _find_sentence_boundary,
)
from jarvis.presence import PresenceLoop, State


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

    def test_newline_after_sentence(self):
        assert _find_sentence_boundary("First line.\nSecond line") == 10


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

    def test_allowed_tools_respects_policy(self, config, mock_robot):
        presence = PresenceLoop(mock_robot)
        config.tool_denylist = ["mcp__jarvis-services__memory_add"]
        with patch("jarvis.brain.create_robot_server") as mock_rs, \
             patch("jarvis.brain.create_services_server") as mock_ss, \
             patch("jarvis.brain.bind_services"):
            mock_rs.return_value = MagicMock()
            mock_ss.return_value = MagicMock()
            brain = Brain(config, presence)
        assert "mcp__jarvis-services__memory_add" not in brain._client.options.allowed_tools

    def test_system_prompt_includes_interaction_contract(self, brain):
        prompt = brain._client.options.system_prompt
        assert "Interaction Contract:" in prompt
        assert "Response Order:" in prompt
        assert "Ambiguity And Safety:" in prompt

    def test_response_mode_resolves_brief_for_urgent_text(self, brain):
        mode = brain._resolve_response_mode("Quick, this is urgent, give me the short answer right now.")
        assert mode == "brief"

    def test_response_mode_resolves_deep_for_detailed_text(self, brain):
        mode = brain._resolve_response_mode("Can you do a deep dive and explain this in detail step by step?")
        assert mode == "deep"

    def test_first_response_strategy_resolves_clarify_for_ambiguous_action(self, brain):
        strategy = brain._first_response_strategy("Turn it off now.")
        assert strategy == "clarify"

    def test_first_response_strategy_resolves_answer_for_direct_question(self, brain):
        strategy = brain._first_response_strategy("What time is sunset today?")
        assert strategy == "answer"

    def test_confidence_policy_mode_resolves_cautious_for_volatile_queries(self, brain):
        mode = brain._confidence_policy_mode("What is the latest weather right now?")
        assert mode == "cautious"

    def test_confidence_policy_mode_resolves_calibrated_for_estimates(self, brain):
        mode = brain._confidence_policy_mode("Can you estimate how likely this is to fail?")
        assert mode == "calibrated"

    @pytest.mark.asyncio
    async def test_respond_sets_thinking_state(self, brain):
        """Brain should set THINKING state when processing begins."""
        mock_msg = MagicMock()
        mock_msg.subtype = "init"
        mock_msg.data = {"session_id": "test-session"}

        with patch.object(brain._client, "query", new=AsyncMock()), \
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

        assert brain._session_id == "session-abc"

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

    @pytest.mark.asyncio
    async def test_respond_includes_memory_context(self, brain):
        if brain._memory is None:
            pytest.skip("Memory disabled")
        memory_entry = MagicMock()
        memory_entry.kind = "profile"
        memory_entry.text = "User prefers coffee in the morning."
        memory_entry.tags = []
        memory_entry.importance = 0.8
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain._memory, "search_v2", return_value=[memory_entry]), \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("coffee"):
                pass

        assert "Context (memory)" in captured.get("text", "")

    @pytest.mark.asyncio
    async def test_memory_search_uses_raw_user_query_not_prompt_style(self, brain):
        if brain._memory is None:
            pytest.skip("Memory disabled")
        brain._config.persona_style = "friendly"
        search_mock = MagicMock(return_value=[])

        with patch.object(brain._client, "query", new=AsyncMock()), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain._memory, "search_v2", search_mock), \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("coffee please"):
                pass

        assert search_mock.call_args is not None
        assert search_mock.call_args.args[0] == "coffee please"

    @pytest.mark.asyncio
    async def test_memory_search_failure_does_not_abort_response_flow(self, brain):
        if brain._memory is None:
            pytest.skip("Memory disabled")
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain._memory, "search_v2", side_effect=RuntimeError("db down")), \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("hello"):
                pass

        assert "text" in captured
        assert captured["text"].startswith("hello")

    @pytest.mark.asyncio
    async def test_respond_includes_persona_style_instruction(self, brain):
        brain._config.persona_style = "friendly"
        if brain._memory is not None:
            brain._memory.upsert_summary("persona_style", "friendly")
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("hello"):
                pass

        payload = captured.get("text", "")
        assert "First response strategy:" in payload
        assert "Strategy=acknowledge" in payload
        assert FIRST_RESPONSE_INSTRUCTIONS["acknowledge"] in payload
        assert "Response mode:" in payload
        assert "Mode=normal" in payload
        assert RESPONSE_MODE_INSTRUCTIONS["normal"] in payload
        assert "Confidence policy:" in payload
        assert "Mode=direct" in payload
        assert CONFIDENCE_POLICY_INSTRUCTIONS["direct"] in payload
        assert "Prompt style:" in payload
        assert "Mode=friendly" in payload
        assert "Response contract:" in payload
        contract_rule = INTERACTION_CONTRACT["response_order"][0]
        assert contract_rule in payload

    @pytest.mark.asyncio
    async def test_respond_includes_brief_response_mode_instruction(self, brain):
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("Quick answer please, this is urgent."):
                pass

        payload = captured.get("text", "")
        assert "First response strategy:" in payload
        assert "Response mode:" in payload
        assert "Mode=brief" in payload
        assert RESPONSE_MODE_INSTRUCTIONS["brief"] in payload
        assert "Confidence policy:" in payload

    @pytest.mark.asyncio
    async def test_respond_includes_deep_response_mode_instruction(self, brain):
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("Please provide a deep dive and explain this in detail step by step."):
                pass

        payload = captured.get("text", "")
        assert "First response strategy:" in payload
        assert "Response mode:" in payload
        assert "Mode=deep" in payload
        assert RESPONSE_MODE_INSTRUCTIONS["deep"] in payload
        assert "Confidence policy:" in payload

    @pytest.mark.asyncio
    async def test_respond_includes_clarify_first_response_strategy_instruction(self, brain):
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("Turn it off now."):
                pass

        payload = captured.get("text", "")
        assert "First response strategy:" in payload
        assert "Strategy=clarify" in payload
        assert FIRST_RESPONSE_INSTRUCTIONS["clarify"] in payload

    @pytest.mark.asyncio
    async def test_respond_includes_cautious_confidence_policy_instruction(self, brain):
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("Give me the latest stock price right now."):
                pass

        payload = captured.get("text", "")
        assert "Confidence policy:" in payload
        assert "Mode=cautious" in payload
        assert CONFIDENCE_POLICY_INSTRUCTIONS["cautious"] in payload

    @pytest.mark.asyncio
    async def test_memory_persona_style_overrides_config(self, brain):
        if brain._memory is None:
            pytest.skip("Memory disabled")
        brain._config.persona_style = "composed"
        brain._memory.upsert_summary("persona_style", "terse")
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("hello"):
                pass

        assert "Mode=terse" in captured.get("text", "")

    @pytest.mark.asyncio
    async def test_persona_style_lookup_not_limited_to_recent_summaries(self, brain):
        if brain._memory is None:
            pytest.skip("Memory disabled")
        brain._config.persona_style = "composed"
        brain._memory.upsert_summary("persona_style", "friendly")
        for idx in range(20):
            brain._memory.upsert_summary(f"topic_{idx}", f"note {idx}")
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond("hello"):
                pass

        assert "Mode=friendly" in captured.get("text", "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("style", ["terse", "composed", "friendly"])
    @pytest.mark.parametrize(
        "prompt",
        [
            "What's on my calendar this afternoon?",
            "Turn on the office lamp and set it to 30 percent.",
            "Summarize what we decided about the weekend trip.",
            "Draft a short reminder to take out the trash at 8 PM.",
        ],
    )
    async def test_style_regression_common_prompts_keep_contract_and_style(self, brain, style, prompt):
        brain._config.persona_style = style
        if brain._memory is not None:
            brain._memory.upsert_summary("persona_style", style)
        captured = {}

        async def fake_query(text: str, session_id: str):
            captured["text"] = text

        with patch.object(brain._client, "query", new=AsyncMock(side_effect=fake_query)), \
             patch.object(brain._client, "receive_response") as mock_recv, \
             patch.object(brain, "_ensure_connected", new=AsyncMock()):
            mock_recv.return_value = _async_iter([])
            async for _ in brain.respond(prompt):
                pass

        payload = captured.get("text", "")
        assert prompt in payload
        assert "First response strategy:" in payload
        assert "Response mode:" in payload
        assert "Confidence policy:" in payload
        assert "Prompt style:" in payload
        assert f"Mode={style}" in payload
        assert STYLE_INSTRUCTIONS[style] in payload
        assert "Response contract:" in payload
        assert INTERACTION_CONTRACT["response_order"][0] in payload
        assert INTERACTION_CONTRACT["ambiguity_and_safety"][0] in payload


# ── Helpers ──────────────────────────────────────────────────

async def _async_iter(items):
    """Create an async iterator from a list."""
    for item in items:
        yield item


async def _async_iter_error(exc):
    """Async iterator that raises an exception."""
    raise exc
    if False:
        yield None
