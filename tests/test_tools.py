"""Tests for jarvis.tools (robot + services)."""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from jarvis.robot.controller import RobotController
from jarvis.presence import PresenceLoop


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
    async def test_play_emotion_sim(self):
        from jarvis.tools.robot import play_emotion

        result = await play_emotion({"name": "happy"})
        assert "happy" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_play_dance_sim(self):
        from jarvis.tools.robot import play_dance

        result = await play_dance({"name": "groove"})
        assert "groove" in result["content"][0]["text"]

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
    async def test_stop_motion_sim(self):
        from jarvis.tools.robot import stop_motion

        result = await stop_motion({})
        assert "stopped" in result["content"][0]["text"].lower()


class TestServicesTools:
    @pytest.fixture(autouse=True)
    def setup_services(self, config, monkeypatch):
        monkeypatch.setenv("HASS_URL", "http://ha.test:8123")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        from jarvis.config import Config
        from jarvis.tools import services
        test_config = Config()
        services.bind(test_config)
        yield
        services._config = None

    @pytest.mark.asyncio
    async def test_smart_home_dry_run_for_locks(self):
        from jarvis.tools.services import smart_home

        result = await smart_home({
            "domain": "lock",
            "action": "unlock",
            "entity_id": "lock.front_door",
        })

        text = result["content"][0]["text"]
        assert "DRY RUN" in text

    @pytest.mark.asyncio
    async def test_smart_home_cooldown(self):
        from jarvis.tools import services

        services._action_last_seen.clear()
        result = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.cooldown",
            "dry_run": True,
        })
        assert "DRY RUN" in result["content"][0]["text"]

        cooldown = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.cooldown",
            "dry_run": True,
        })
        assert "cooldown" in cooldown["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_tools(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        created = await services.memory_add({"text": "Call me Boss.", "kind": "profile", "sensitivity": 0.2, "source": "profile"})
        assert "stored" in created["content"][0]["text"].lower()

        sensitive = await services.memory_add({"text": "My bank code is 1234", "kind": "note", "sensitivity": 0.9, "source": "secrets"})
        assert "stored" in sensitive["content"][0]["text"].lower()

        found = await services.memory_search({"query": "call me", "limit": 5, "sources": ["profile"]})
        assert "call me" in found["content"][0]["text"].lower()

        filtered = await services.memory_search({"query": "bank", "limit": 5, "max_sensitivity": 0.4})
        assert "no relevant" in filtered["content"][0]["text"].lower()

        included = await services.memory_search({"query": "bank", "limit": 5, "include_sensitive": True})
        assert "bank" in included["content"][0]["text"].lower()

        status = await services.memory_status({"warm": True, "sync": True})
        assert "entries" in status["content"][0]["text"].lower()

        recent = await services.memory_recent({"limit": 1, "sources": ["secrets"]})
        assert "note" in recent["content"][0]["text"].lower()

        summary = await services.tool_summary({"limit": 10})
        assert "memory_add" in summary["content"][0]["text"].lower()

        summary_text = await services.tool_summary_text({"limit": 10})
        assert "memory_add" in summary_text["content"][0]["text"].lower()

        summary_added = await services.memory_summary_add({"topic": "preferences", "summary": "User likes coffee."})
        assert "summary" in summary_added["content"][0]["text"].lower()

        summary_list = await services.memory_summary_list({"limit": 2})
        assert "preferences" in summary_list["content"][0]["text"].lower()

        plan = await services.task_plan_create({"title": "Morning routine", "steps": ["Check calendar", "Summarize news"]})
        assert "plan created" in plan["content"][0]["text"].lower()

        plans = await services.task_plan_list({"open_only": True})
        assert "morning routine" in plans["content"][0]["text"].lower()

        updated = await services.task_plan_update({"plan_id": 1, "step_index": 0, "status": "done"})
        assert "updated" in updated["content"][0]["text"].lower()

        summary = await services.task_plan_summary({"plan_id": 1})
        assert "steps complete" in summary["content"][0]["text"].lower()

        next_step = await services.task_plan_next({"plan_id": 1})
        assert "next step" in next_step["content"][0]["text"].lower()

        filtered_str_false = await services.memory_search({
            "query": "bank",
            "include_sensitive": "false",
            "max_sensitivity": 0.4,
        })
        assert "no relevant" in filtered_str_false["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_create_rejects_empty_steps(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        result = await services.task_plan_create({"title": "Bad plan", "steps": [" ", "\n"]})
        assert "non-empty step" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_list_parses_open_only_string(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.task_plan_create({"title": "Closable", "steps": ["Only step"]})
        await services.task_plan_update({"plan_id": 1, "step_index": 0, "status": "done"})

        open_only = await services.task_plan_list({"open_only": "true"})
        assert "no task plans found" in open_only["content"][0]["text"].lower()

        include_closed = await services.task_plan_list({"open_only": "false"})
        assert "closable" in include_closed["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_tool_policy_denies(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        config = Config()
        config.tool_denylist = ["memory_add"]
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(Config(), store)
        await services.memory_add({"text": "Okay"})
        services.bind(config, store)

        denied = await services.memory_add({"text": "Nope"})
        assert "not permitted" in denied["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_dry_run_explicit_false(self):
        from jarvis.tools.services import smart_home

        # Even for locks, explicit dry_run=false should execute
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session_cls.return_value = mock_session

            result = await smart_home({
                "domain": "lock",
                "action": "unlock",
                "entity_id": "lock.front_door",
                "dry_run": False,
            })

        text = result["content"][0]["text"]
        assert "DRY RUN" not in text

    @pytest.mark.asyncio
    async def test_smart_home_no_config(self):
        from jarvis.tools import services
        services._config = None

        result = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.living_room",
        })

        assert "not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_state_not_configured(self):
        from jarvis.tools import services
        services._config = None

        result = await services.smart_home_state({"entity_id": "light.kitchen"})
        assert "not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_get_time(self):
        from jarvis.tools.services import get_time

        result = await get_time({})
        text = result["content"][0]["text"]
        assert len(text) >= 10

    @pytest.mark.asyncio
    async def test_tool_feedback_called(self, monkeypatch):
        from jarvis.tools import services
        calls = []

        def _feedback(kind: str) -> None:
            calls.append(kind)

        monkeypatch.setattr("jarvis.tools.robot.tool_feedback", _feedback)

        await services.get_time({})
        assert calls == ["start", "done"]

    @pytest.mark.asyncio
    async def test_audit_log_written(self, tmp_path):
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"

        result = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.test",
            "dry_run": True,
        })

        # Audit log should exist and contain the action
        assert services.AUDIT_LOG.exists()
        content = services.AUDIT_LOG.read_text()
        assert "light.test" in content
        assert "turn_on" in content
