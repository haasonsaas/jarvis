"""Tests for jarvis.tools (robot + services)."""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock



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

    def test_service_error_codes_include_required_entries(self):
        from jarvis.tools import services

        assert "summary_unavailable" in services.SERVICE_ERROR_CODES
        assert "unknown_error" in services.SERVICE_ERROR_CODES

    def test_record_service_error_normalizes_unknown_code(self, monkeypatch):
        from jarvis.tools import services

        calls = []

        def _record(name, status, start_time, detail=None, effect=None, risk=None):
            calls.append((name, status, detail))

        monkeypatch.setattr("jarvis.tools.services.record_summary", _record)
        services._record_service_error("smart_home", 0.0, "not_a_known_code")
        assert calls == [("smart_home", "error", "unknown_error")]

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

        status = await services.memory_status({"warm": True, "sync": True, "optimize": True, "vacuum": True})
        assert "entries" in status["content"][0]["text"].lower()

        recent = await services.memory_recent({"limit": 1, "sources": ["secrets"]})
        assert "note" in recent["content"][0]["text"].lower()

        summary = await services.tool_summary({"limit": 10})
        assert "memory_add" in summary["content"][0]["text"].lower()
        summary_payload = json.loads(summary["content"][0]["text"])
        assert all("effect" in item for item in summary_payload)
        assert all("risk" in item for item in summary_payload)

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
    async def test_home_permission_profile_readonly_denies_mutation(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.home_permission_profile = "readonly"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        result = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.kitchen",
        })
        assert "not permitted" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_permission_profile_readonly_denies_add(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_permission_profile = "readonly"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        result = await services.todoist_add_task({"content": "Buy coffee"})
        assert "not permitted" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_notification_permission_profile_off_denies_notify(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.notification_permission_profile = "off"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        result = await services.pushover_notify({"message": "hello"})
        assert "not permitted" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_dry_run_explicit_false_with_confirm(self):
        from jarvis.tools.services import smart_home

        # Sensitive domains require confirm=true when executing
        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = AsyncMock()
            state_resp.status = 200
            state_resp.json = AsyncMock(return_value={"state": "locked", "attributes": {}})
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=state_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
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
                "confirm": True,
            })

        text = result["content"][0]["text"]
        assert "DRY RUN" not in text

    @pytest.mark.asyncio
    async def test_smart_home_sensitive_execute_requires_confirm(self):
        from jarvis.tools.services import smart_home

        result = await smart_home({
            "domain": "lock",
            "action": "unlock",
            "entity_id": "lock.front_door",
            "dry_run": False,
        })
        assert "requires confirm=true" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_rejects_entity_domain_mismatch(self):
        from jarvis.tools.services import smart_home

        result = await smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "switch.kitchen",
        })
        assert "domain must match" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_idempotent_turn_on_short_circuits(self):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = AsyncMock()
            state_resp.status = 200
            state_resp.json = AsyncMock(return_value={"state": "on", "attributes": {}})
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=state_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session.post = MagicMock()
            mock_session_cls.return_value = mock_session

            result = await smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })

        assert "no-op" in result["content"][0]["text"].lower()
        mock_session.post.assert_not_called()

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
    async def test_smart_home_handles_unexpected_exception(self):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession", side_effect=RuntimeError("boom")):
            result = await smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })
        assert "unable to validate entity state" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_handles_timeout(self):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession", side_effect=asyncio.TimeoutError()):
            result = await smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })
        assert "preflight timed out" in result["content"][0]["text"].lower()
        from jarvis.tool_summary import list_summaries
        summaries = list_summaries(20)
        assert any(item.get("name") == "smart_home" and item.get("detail") == "timeout" for item in summaries)

    @pytest.mark.asyncio
    async def test_smart_home_handles_cancelled_request(self):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession", side_effect=asyncio.CancelledError()):
            result = await smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })
        assert "preflight was cancelled" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_handles_error_body_read_failure(self):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = AsyncMock()
            state_resp.status = 200
            state_resp.json = AsyncMock(return_value={"state": "off", "attributes": {}})
            mock_resp = AsyncMock()
            mock_resp.status = 500
            mock_resp.text = AsyncMock(side_effect=RuntimeError("read failed"))
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=state_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session.post = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session_cls.return_value = mock_session

            result = await smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })
        assert "<body unavailable>" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_smart_home_state_not_configured(self):
        from jarvis.tools import services
        services._config = None

        result = await services.smart_home_state({"entity_id": "light.kitchen"})
        assert "not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_state_handles_unexpected_exception(self):
        from jarvis.tools.services import smart_home_state

        with patch("aiohttp.ClientSession", side_effect=RuntimeError("boom")):
            result = await smart_home_state({"entity_id": "light.kitchen"})
        assert "unexpected home assistant error" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_state_handles_timeout(self):
        from jarvis.tools.services import smart_home_state

        with patch("aiohttp.ClientSession", side_effect=asyncio.TimeoutError()):
            result = await smart_home_state({"entity_id": "light.kitchen"})
        assert "timed out" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_state_handles_cancelled_request(self):
        from jarvis.tools.services import smart_home_state

        with patch("aiohttp.ClientSession", side_effect=asyncio.CancelledError()):
            result = await smart_home_state({"entity_id": "light.kitchen"})
        assert "cancelled" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_state_handles_invalid_json_response(self):
        from jarvis.tools.services import smart_home_state

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(side_effect=ValueError("bad json"))
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session_cls.return_value = mock_session

            result = await smart_home_state({"entity_id": "light.kitchen"})
        assert "invalid response" in result["content"][0]["text"].lower()
        from jarvis.tool_summary import list_summaries
        summaries = list_summaries(20)
        assert any(item.get("name") == "smart_home_state" and item.get("detail") == "invalid_json" for item in summaries)

    @pytest.mark.asyncio
    async def test_smart_home_validates_data_object(self):
        from jarvis.tools.services import smart_home

        result = await smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.kitchen",
            "data": "brightness=50",
        })
        assert "must be an object" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_state_requires_entity_id(self):
        from jarvis.tools.services import smart_home_state

        result = await smart_home_state({})
        assert "entity id required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_add_task_requires_config(self):
        from jarvis.tools import services

        result = await services.todoist_add_task({"content": "Buy coffee"})
        assert "todoist not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_requires_config(self):
        from jarvis.tools import services

        result = await services.todoist_list_tasks({"limit": 5})
        assert "todoist not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_pushover_notify_requires_config(self):
        from jarvis.tools import services

        result = await services.pushover_notify({"message": "hello"})
        assert "pushover not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_add_task_success(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.todoist_project_id = "proj-1"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"id": "123"})
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session_cls.return_value = mock_session

            result = await services.todoist_add_task({"content": "Buy coffee"})

        assert "created" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_success(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=[{"content": "Buy coffee"}, {"content": "Call mom"}])
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_resp),
                __aexit__=AsyncMock(return_value=False),
            ))
            mock_session_cls.return_value = mock_session

            result = await services.todoist_list_tasks({"limit": 2})

        text = result["content"][0]["text"].lower()
        assert "buy coffee" in text
        assert "call mom" in text

    @pytest.mark.asyncio
    async def test_pushover_notify_success(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

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

            result = await services.pushover_notify({"message": "hello"})

        assert "sent" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_add_ignores_non_list_tags(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.memory_add({"text": "Tagged note", "tags": "not-a-list"})
        recent = await services.memory_recent({"limit": 1})
        assert "tags=" not in recent["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_search_accepts_string_source(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.memory_add({"text": "Source test", "source": "profile"})
        filtered = await services.memory_search({"query": "source", "sources": "profile"})
        assert "source test" in filtered["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_search_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "search_v2", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.memory_search({"query": "test"})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_add_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "add_memory", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.memory_add({"text": "test"})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_add_non_finite_sensitivity_uses_default(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.memory_add({"text": "Finite sensitivity", "sensitivity": "nan"})
        recent = store.recent(limit=1)
        assert len(recent) == 1
        assert recent[0].sensitivity == 0.0

    @pytest.mark.asyncio
    async def test_memory_add_bool_sensitivity_uses_default(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.memory_add({"text": "Bool sensitivity", "sensitivity": True})
        recent = store.recent(limit=1)
        assert len(recent) == 1
        assert recent[0].sensitivity == 0.0

    @pytest.mark.asyncio
    async def test_memory_search_non_finite_include_sensitive_uses_default_false(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.memory_add({"text": "secret token", "sensitivity": 0.9})
        result = await services.memory_search({
            "query": "secret",
            "include_sensitive": float("nan"),
            "max_sensitivity": 0.4,
        })
        assert "no relevant" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_recent_non_finite_limit_does_not_crash(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.memory_add({"text": "hello"})
        result = await services.memory_recent({"limit": float("inf")})
        assert "hello" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_recent_bool_limit_uses_default(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        captured: dict[str, int] = {}
        original_recent = store.recent

        def wrapped_recent(*, limit: int = 5, kind=None, sources=None):
            captured["limit"] = limit
            return original_recent(limit=limit, kind=kind, sources=sources)

        monkeypatch.setattr(store, "recent", wrapped_recent)
        await services.memory_add({"text": "hello"})
        await services.memory_recent({"limit": True})
        assert captured["limit"] == 5

    @pytest.mark.asyncio
    async def test_memory_recent_fractional_limit_uses_default(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        captured: dict[str, int] = {}
        original_recent = store.recent

        def wrapped_recent(*, limit: int = 5, kind=None, sources=None):
            captured["limit"] = limit
            return original_recent(limit=limit, kind=kind, sources=sources)

        monkeypatch.setattr(store, "recent", wrapped_recent)
        await services.memory_add({"text": "hello"})
        await services.memory_recent({"limit": 2.9})
        assert captured["limit"] == 5

    @pytest.mark.asyncio
    async def test_memory_search_fractional_limit_uses_default(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        captured: dict[str, int] = {}
        original_search = store.search_v2

        def wrapped_search(query, *, limit: int = 5, **kwargs):
            captured["limit"] = limit
            return original_search(query, limit=limit, **kwargs)

        monkeypatch.setattr(store, "search_v2", wrapped_search)
        await services.memory_add({"text": "hello world"})
        await services.memory_search({"query": "hello", "limit": 3.4})
        assert captured["limit"] == 5

    @pytest.mark.asyncio
    async def test_memory_status_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "memory_status", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.memory_status({})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_recent_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "recent", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.memory_recent({"limit": 5})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_summary_add_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "upsert_summary", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.memory_summary_add({"topic": "prefs", "summary": "x"})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_memory_summary_list_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "list_summaries", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.memory_summary_list({"limit": 5})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_update_rejects_invalid_status(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.task_plan_create({"title": "Plan", "steps": ["step"]})
        result = await services.task_plan_update({"plan_id": 1, "step_index": 0, "status": "finished"})
        assert "must be one of" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_update_rejects_fractional_identifiers(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.task_plan_create({"title": "Plan", "steps": ["step"]})
        result = await services.task_plan_update({"plan_id": 1.9, "step_index": 0.5, "status": "done"})
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_list_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "list_task_plans", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.task_plan_list({"open_only": True})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_create_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "add_task_plan", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.task_plan_create({"title": "Plan", "steps": ["a"]})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_next_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "next_task_step", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.task_plan_next({})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_update_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        await services.task_plan_create({"title": "Plan", "steps": ["a"]})
        monkeypatch.setattr(store, "update_task_step", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.task_plan_update({"plan_id": 1, "step_index": 0, "status": "done"})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_summary_handles_storage_error(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr(store, "task_plan_progress", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

        result = await services.task_plan_summary({"plan_id": 1})
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_next_rejects_invalid_plan_id(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        result = await services.task_plan_next({"plan_id": "abc"})
        assert "positive integer" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_next_rejects_fractional_plan_id(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        result = await services.task_plan_next({"plan_id": 1.2})
        assert "positive integer" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_task_plan_summary_rejects_fractional_plan_id(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        result = await services.task_plan_summary({"plan_id": 1.2})
        assert "plan id required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_get_time(self):
        from jarvis.tools.services import get_time

        result = await get_time({})
        text = result["content"][0]["text"]
        assert len(text) >= 10

    @pytest.mark.asyncio
    async def test_system_status_reports_snapshot(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        await services.memory_add({"text": "status probe"})

        result = await services.system_status({})
        payload = json.loads(result["content"][0]["text"])
        assert "local_time" in payload
        assert "tool_policy" in payload
        assert "memory" in payload
        assert "audit" in payload
        assert payload["health"]["health_level"] in {"ok", "degraded", "error"}

    @pytest.mark.asyncio
    async def test_system_status_handles_recent_tools_failure(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr("jarvis.tools.services.list_summaries", lambda limit=5: (_ for _ in ()).throw(RuntimeError("summary unavailable")))

        result = await services.system_status({})
        payload = json.loads(result["content"][0]["text"])
        assert payload["recent_tools"]["error"] == "summary unavailable"
        assert payload["health"]["health_level"] == "degraded"
        assert "tool_summary_error" in payload["health"]["reasons"]

    @pytest.mark.asyncio
    async def test_system_status_reports_error_when_unbound(self):
        from jarvis.tools import services

        services._config = None
        result = await services.system_status({})
        payload = json.loads(result["content"][0]["text"])
        assert payload["health"]["health_level"] == "error"
        assert "config_unbound" in payload["health"]["reasons"]

    @pytest.mark.asyncio
    async def test_system_status_serializes_non_json_recent_tools(self, tmp_path, monkeypatch):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)
        monkeypatch.setattr("jarvis.tools.services.list_summaries", lambda limit=5: [{"name": "x", "meta": {1, 2}}])

        result = await services.system_status({})
        payload = json.loads(result["content"][0]["text"])
        meta = payload["recent_tools"][0]["meta"]
        assert meta.startswith("{") and meta.endswith("}")
        assert "1" in meta and "2" in meta

    @pytest.mark.asyncio
    async def test_system_status_denied_by_policy(self):
        from jarvis.config import Config
        from jarvis.tools import services

        cfg = Config()
        cfg.tool_denylist = ["system_status"]
        services.bind(cfg)

        result = await services.system_status({})
        assert "not permitted" in result["content"][0]["text"].lower()

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
    async def test_smart_home_dry_run_emits_feedback_start_done(self, monkeypatch):
        from jarvis.tools import services
        calls = []

        def _feedback(kind: str) -> None:
            calls.append(kind)

        monkeypatch.setattr("jarvis.tools.robot.tool_feedback", _feedback)
        services._action_last_seen.clear()

        await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.feedback",
            "dry_run": True,
        })
        assert calls == ["start", "done"]

    @pytest.mark.asyncio
    async def test_audit_log_written(self, tmp_path):
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"

        await services.smart_home({
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

    @pytest.mark.asyncio
    async def test_smart_home_dry_run_handles_non_serializable_data(self):
        from jarvis.tools.services import smart_home

        result = await smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.misc",
            "dry_run": True,
            "data": {"levels": {1, 2, 3}},
        })
        assert "DRY RUN" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_audit_log_rotates_when_large(self, tmp_path):
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        services._audit_log_max_bytes = 64
        services._audit_log_backups = 2
        services._action_last_seen.clear()

        for idx in range(6):
            await services.smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": f"light.rotate_{idx}",
                "dry_run": True,
                "data": {"payload": "x" * 80},
            })

        assert services.AUDIT_LOG.exists()
        assert (tmp_path / "audit.jsonl.1").exists()

    def test_action_history_prunes_stale_and_caps_size(self):
        from jarvis.tools import services

        services._action_last_seen.clear()
        base = 10_000.0
        for idx in range(2105):
            services._action_last_seen[f"k{idx}"] = base - 10_000.0  # stale
        for idx in range(10):
            services._action_last_seen[f"fresh{idx}"] = base

        services._prune_action_history(base)

        assert len(services._action_last_seen) <= services.ACTION_HISTORY_MAX_ENTRIES
        assert all(key.startswith("fresh") for key in services._action_last_seen)

    @pytest.mark.asyncio
    async def test_tool_summary_text_handles_bad_duration_value(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services.list_summaries",
            lambda limit=6: [
                {"name": "tool_x", "status": "ok", "duration_ms": "invalid"},
                {"name": "tool_y", "status": "ok", "duration_ms": float("nan")},
                {"name": "tool_z", "status": "ok", "duration_ms": float("inf")},
            ],
        )
        result = await services.tool_summary_text({"limit": 3})
        text = result["content"][0]["text"]
        assert "tool_x" in text
        assert "tool_y" in text
        assert "tool_z" in text
        assert "(0ms)" in text

    @pytest.mark.asyncio
    async def test_tool_summary_handles_summary_store_failure(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr("jarvis.tools.services.list_summaries", lambda limit=10: (_ for _ in ()).throw(RuntimeError("store down")))
        result = await services.tool_summary({"limit": 5})
        assert "unavailable" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_tool_summary_serializes_non_json_values(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr("jarvis.tools.services.list_summaries", lambda limit=10: [{"name": "x", "extra": {1, 2}}])
        result = await services.tool_summary({"limit": 5})
        payload = json.loads(result["content"][0]["text"])
        extra = payload[0]["extra"]
        assert extra.startswith("{") and extra.endswith("}")
        assert "1" in extra and "2" in extra

    @pytest.mark.asyncio
    async def test_tool_summary_text_handles_summary_store_failure(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr("jarvis.tools.services.list_summaries", lambda limit=6: (_ for _ in ()).throw(RuntimeError("store down")))
        result = await services.tool_summary_text({"limit": 5})
        assert "unavailable" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_tool_summary_text_skips_malformed_summary_items(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr("jarvis.tools.services.list_summaries", lambda limit=6: ["bad", 123, None])
        result = await services.tool_summary_text({"limit": 5})
        assert "no recent tool activity" in result["content"][0]["text"].lower()

    def test_service_schema_runtime_required_fields_parity(self):
        from jarvis.tools import services

        assert set(services.SERVICE_TOOL_SCHEMAS) == set(services.SERVICE_RUNTIME_REQUIRED_FIELDS)
        for name, schema in services.SERVICE_TOOL_SCHEMAS.items():
            assert _schema_required_fields(schema) == services.SERVICE_RUNTIME_REQUIRED_FIELDS[name]
