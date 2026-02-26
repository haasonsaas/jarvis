"""Tests for jarvis.tools.robot."""

import json
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.fast

def _schema_required_fields(schema: object) -> set[str]:
    if isinstance(schema, dict):
        required = schema.get("required")
        if isinstance(required, list):
            return {str(item) for item in required}
    return set()

class TestRobotTools:
    @pytest.fixture(autouse=True)
    def setup_tools(self, mock_robot, presence):
        from jarvis.tools import robot as robot_tools
        robot_tools.bind(mock_robot, presence)
        yield
        robot_tools._robot = None
        robot_tools._presence = None

    @pytest.mark.asyncio
    async def test_embody_sets_signals(self, presence):
        from jarvis.tools.robot import embody

        result = await embody({
            "intent": "acknowledge",
            "prosody": "warm",
            "nod": 0.7,
            "tilt": 5.0,
            "glance_yaw": -10.0,
        })

        assert presence.signals.intent_nod == 0.7
        assert presence.signals.intent_tilt == 5.0
        assert presence.signals.intent_glance_yaw == -10.0
        assert "acknowledge" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_embody_clamps_values(self, presence):
        from jarvis.tools.robot import embody

        await embody({
            "intent": "answer",
            "prosody": "calm",
            "nod": 5.0,       # over max of 1.0
            "tilt": 999.0,    # over max of 15.0
            "glance_yaw": -100.0,  # under min of -30.0
        })

        assert presence.signals.intent_nod == 1.0
        assert presence.signals.intent_tilt == 15.0
        assert presence.signals.intent_glance_yaw == -30.0

    @pytest.mark.asyncio
    async def test_embody_defaults(self, presence):
        from jarvis.tools.robot import embody

        await embody({"intent": "greet", "prosody": "warm"})

        assert presence.signals.intent_nod == 0.0
        assert presence.signals.intent_tilt == 0.0

    @pytest.mark.asyncio
    async def test_embody_handles_string_numbers(self, presence):
        from jarvis.tools.robot import embody

        await embody({
            "intent": "answer",
            "prosody": "calm",
            "nod": "0.6",
            "tilt": "-4.5",
            "glance_yaw": "8",
        })

        assert presence.signals.intent_nod == 0.6
        assert presence.signals.intent_tilt == -4.5
        assert presence.signals.intent_glance_yaw == 8.0

    @pytest.mark.asyncio
    async def test_embody_non_finite_numbers_fallback_to_defaults(self, presence):
        from jarvis.tools.robot import embody

        await embody({
            "intent": "answer",
            "prosody": "calm",
            "nod": "nan",
            "tilt": "inf",
            "glance_yaw": "-inf",
        })

        assert presence.signals.intent_nod == 0.0
        assert presence.signals.intent_tilt == 0.0
        assert presence.signals.intent_glance_yaw == 0.0

    @pytest.mark.asyncio
    async def test_embody_bool_numeric_fields_use_defaults(self, presence):
        from jarvis.tools.robot import embody

        await embody({
            "intent": "answer",
            "prosody": "calm",
            "nod": True,
            "tilt": False,
            "glance_yaw": True,
        })

        assert presence.signals.intent_nod == 0.0
        assert presence.signals.intent_tilt == 0.0
        assert presence.signals.intent_glance_yaw == 0.0

    @pytest.mark.asyncio
    async def test_play_emotion_sim(self):
        from jarvis.tools.robot import play_emotion

        result = await play_emotion({"name": "happy"})
        assert "happy" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_play_emotion_requires_name(self):
        from jarvis.tools.robot import play_emotion

        result = await play_emotion({})
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_play_dance_sim(self):
        from jarvis.tools.robot import play_dance

        result = await play_dance({"name": "groove"})
        assert "groove" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_play_dance_requires_name(self):
        from jarvis.tools.robot import play_dance

        result = await play_dance({})
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_list_animations_sim(self):
        from jarvis.tools.robot import list_animations

        result = await list_animations({})
        data = json.loads(result["content"][0]["text"])
        assert "emotions" in data
        assert "dances" in data

    @pytest.mark.asyncio
    async def test_run_sequence_sim(self):
        from jarvis.tools.robot import run_sequence

        result = await run_sequence({
            "steps": [
                {"kind": "head", "yaw": 10.0, "pitch": 5.0},
                {"kind": "pause", "duration": 0.1},
                {"kind": "antennas", "left": 5.0, "right": -5.0},
            ]
        })

        assert "Queued" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_run_macro_sim(self):
        from jarvis.tools.robot import run_macro

        result = await run_macro({"name": "acknowledge", "intensity": 1.0})
        assert "Macro queued" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_run_macro_bool_intensity_uses_default(self, mock_robot):
        from jarvis.tools.robot import run_macro

        mock_runner = MagicMock()
        mock_robot.run_macro = mock_runner
        await run_macro({"name": "acknowledge", "intensity": True})

        _, kwargs = mock_runner.call_args
        assert kwargs["intensity"] == 1.0

    @pytest.mark.asyncio
    async def test_run_sequence_parses_blocking_string(self, mock_robot):
        from jarvis.tools.robot import run_sequence
        mock_runner = MagicMock()
        mock_robot.run_sequence = mock_runner

        await run_sequence({
            "blocking": "false",
            "steps": [{"kind": "head", "yaw": "5", "duration": "0.2"}],
        })
        _, kwargs = mock_runner.call_args
        assert kwargs["blocking"] is False

    @pytest.mark.asyncio
    async def test_run_sequence_non_finite_blocking_uses_default_false(self, mock_robot):
        from jarvis.tools.robot import run_sequence
        mock_runner = MagicMock()
        mock_robot.run_sequence = mock_runner

        await run_sequence({
            "blocking": float("nan"),
            "steps": [{"kind": "head", "yaw": 5}],
        })
        _, kwargs = mock_runner.call_args
        assert kwargs["blocking"] is False

    @pytest.mark.asyncio
    async def test_run_sequence_rejects_non_list_steps(self):
        from jarvis.tools.robot import run_sequence

        result = await run_sequence({"steps": "not-a-list"})
        assert "must be a list" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_embody_requires_intent_and_prosody(self):
        from jarvis.tools.robot import embody

        result = await embody({"nod": 0.5})
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_stop_motion_sim(self):
        from jarvis.tools.robot import stop_motion

        result = await stop_motion({})
        assert "stopped" in result["content"][0]["text"].lower()

    def test_robot_schema_runtime_required_fields_parity(self):
        from jarvis.tools import robot as robot_tools

        assert set(robot_tools.ROBOT_TOOL_SCHEMAS) == set(robot_tools.ROBOT_RUNTIME_REQUIRED_FIELDS)
        for name, schema in robot_tools.ROBOT_TOOL_SCHEMAS.items():
            assert _schema_required_fields(schema) == robot_tools.ROBOT_RUNTIME_REQUIRED_FIELDS[name]
