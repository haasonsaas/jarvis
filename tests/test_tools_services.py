"""Tests for jarvis.tools.services."""

import asyncio
import json
import logging
import time
from pathlib import Path
import aiohttp
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.fast

def _schema_required_fields(schema: object) -> set[str]:
    if isinstance(schema, dict):
        required = schema.get("required")
        if isinstance(required, list):
            return {str(item) for item in required}
    return set()


def _assert_audit_payload(
    details: dict,
    *,
    required: set[str] | None = None,
    forbidden: set[str] | None = None,
) -> None:
    assert isinstance(details, dict)
    for key in required or set():
        assert key in details
    for key in forbidden or set():
        assert key not in details

class TestServicesTools:
    @pytest.fixture(autouse=True)
    def setup_services(self, config, monkeypatch):
        monkeypatch.setenv("HASS_URL", "http://ha.test:8123")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        from jarvis.config import Config
        from jarvis.tools import services
        test_config = Config()
        services.bind(test_config)
        services.set_skill_registry(None)
        yield
        services._config = None

    def test_service_error_codes_include_required_entries(self):
        from jarvis.tools import services
        from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES

        assert "summary_unavailable" in services.SERVICE_ERROR_CODES
        assert "unknown_error" in services.SERVICE_ERROR_CODES
        assert "api_error" in services.SERVICE_ERROR_CODES
        assert services.SERVICE_ERROR_CODES == TOOL_SERVICE_ERROR_CODES

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
    async def test_smart_home_audit_redacts_sensitive_service_data(self, monkeypatch):
        from jarvis.tools import services

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        await services.smart_home({
            "domain": "lock",
            "action": "unlock",
            "entity_id": "lock.front_door",
            "data": {
                "code": "1234",
                "label": "front",
                "nested": {"pin": "9999", "alarm_code": "0000", "brightness": 10},
                "list": [
                    {"access_token": "abc"},
                    {"safe": "ok"},
                    {"webhook_id": "hook-1"},
                    {"oauth_token": "oauth-123"},
                    {"passcode": "2468"},
                ],
            },
            "dry_run": True,
        })

        _, details = audit_calls[-1]
        payload = details["data"]
        assert payload["code"] == "***REDACTED***"
        assert payload["nested"]["pin"] == "***REDACTED***"
        assert payload["nested"]["alarm_code"] == "***REDACTED***"
        assert payload["list"][0]["access_token"] == "***REDACTED***"
        assert payload["list"][2]["webhook_id"] == "***REDACTED***"
        assert payload["list"][3]["oauth_token"] == "***REDACTED***"
        assert payload["list"][4]["passcode"] == "***REDACTED***"
        assert payload["label"] == "front"
        assert payload["nested"]["brightness"] == 10
        assert details["policy_decision"] == "dry_run"

    def test_metadata_only_audit_helper_strips_raw_fields(self):
        from jarvis.tools import services

        todoist = services._metadata_only_audit_details(
            "todoist_add_task",
            {
                "result": "ok",
                "content": "secret content",
                "description": "secret desc",
                "content_length": 14,
            },
        )
        pushover = services._metadata_only_audit_details(
            "pushover_notify",
            {
                "result": "ok",
                "message": "otp 123456",
                "title": "Private",
                "message_length": 10,
            },
        )

        assert "content" not in todoist
        assert "description" not in todoist
        assert todoist["content_length"] == 14
        assert "message" not in pushover
        assert "title" not in pushover
        assert pushover["message_length"] == 10

        slack = services._metadata_only_audit_details(
            "slack_notify",
            {
                "result": "ok",
                "message": "secret content",
                "message_length": 14,
            },
        )
        discord = services._metadata_only_audit_details(
            "discord_notify",
            {
                "result": "ok",
                "message": "secret content",
                "message_length": 14,
            },
        )
        assert "message" not in slack
        assert "message" not in discord

    @pytest.mark.asyncio
    async def test_smart_home_cooldown_on_execute(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools import services

        services._action_last_seen.clear()
        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "off", "attributes": {}})
            post_resp = aiohttp_response(status=200)
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
            mock_session_cls.return_value = mock_session

            result = await services.smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.cooldown",
                "dry_run": False,
            })
            assert "done:" in result["content"][0]["text"].lower()

            cooldown = await services.smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.cooldown",
                "dry_run": False,
            })
        assert "cooldown" in cooldown["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_dry_run_does_not_trigger_cooldown(self):
        from jarvis.tools import services

        services._action_last_seen.clear()
        first = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.cooldown_dry",
            "dry_run": True,
        })
        second = await services.smart_home({
            "domain": "light",
            "action": "turn_on",
            "entity_id": "light.cooldown_dry",
            "dry_run": True,
        })

        assert "dry run" in first["content"][0]["text"].lower()
        assert "dry run" in second["content"][0]["text"].lower()
        assert "light:turn_on:light.cooldown_dry" not in services._action_last_seen

    @pytest.mark.asyncio
    async def test_memory_tools(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        created = await services.memory_add({"text": "Call me Boss.", "kind": "profile", "sensitivity": 0.2, "source": "profile"})
        assert "stored" in created["content"][0]["text"].lower()
        created_text = created["content"][0]["text"]
        memory_id = int(created_text.split("id=")[1].split(")", 1)[0])

        sensitive = await services.memory_add({"text": "My bank code is 1234", "kind": "note", "sensitivity": 0.9, "source": "secrets"})
        assert "stored" in sensitive["content"][0]["text"].lower()

        updated = await services.memory_update({"memory_id": memory_id, "text": "Call me Commander.", "allow_pii": False})
        assert "updated" in updated["content"][0]["text"].lower()

        found = await services.memory_search({"query": "call me", "limit": 5, "sources": ["profile"]})
        assert "call me" in found["content"][0]["text"].lower()
        assert "commander" in found["content"][0]["text"].lower()

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

        forgotten = await services.memory_forget({"memory_id": memory_id})
        assert "forgotten" in forgotten["content"][0]["text"].lower()
        gone = await services.memory_search({"query": "commander", "limit": 5})
        assert "no relevant" in gone["content"][0]["text"].lower()

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
    async def test_memory_add_blocks_pii_by_default(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        blocked = await services.memory_add({"text": "My SSN is 123-45-6789"})
        assert "potential pii detected" in blocked["content"][0]["text"].lower()

        allowed = await services.memory_add({"text": "My SSN is 123-45-6789", "allow_pii": True})
        assert "stored" in allowed["content"][0]["text"].lower()

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
    async def test_safe_mode_forces_smart_home_execute_path_to_dry_run(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.safe_mode_enabled = True
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.smart_home(
                {
                    "domain": "light",
                    "action": "turn_on",
                    "entity_id": "light.kitchen",
                    "dry_run": False,
                }
            )

        text = result["content"][0]["text"].lower()
        assert "dry run" in text
        assert "safe mode forced dry-run" in text
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_safe_mode_blocks_webhook_trigger_mutation(self):
        from jarvis.config import Config
        from jarvis.tools import services

        cfg = Config()
        cfg.safe_mode_enabled = True
        cfg.webhook_allowlist = ["example.com"]
        services.bind(cfg)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.webhook_trigger(
                {"url": "https://api.example.com/hook", "method": "POST"}
            )

        text = result["content"][0]["text"].lower()
        assert "safe mode is enabled" in text
        mock_session_cls.assert_not_called()

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
    async def test_notification_permission_profile_off_denies_channel_webhooks(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.notification_permission_profile = "off"
        cfg.slack_webhook_url = "https://hooks.slack.test/abc"
        cfg.discord_webhook_url = "https://discord.test/api/webhooks/abc"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        slack = await services.slack_notify({"message": "hello"})
        discord = await services.discord_notify({"message": "hello"})
        assert "not permitted" in slack["content"][0]["text"].lower()
        assert "not permitted" in discord["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_email_permission_profile_readonly_denies_send(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.email_permission_profile = "readonly"
        cfg.email_smtp_host = "smtp.example.com"
        cfg.email_from = "jarvis@example.com"
        cfg.email_default_to = "owner@example.com"
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        result = await services.email_send({"subject": "Test", "body": "Hello", "confirm": True})
        assert "not permitted" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_identity_profile_deny_blocks_webhook_and_records_requester(self, monkeypatch):
        from jarvis.config import Config
        from jarvis.tools import services

        cfg = Config()
        cfg.identity_enforcement_enabled = True
        cfg.identity_user_profiles = {"alice": "deny"}
        cfg.webhook_allowlist = ["example.com"]
        services.bind(cfg)

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        result = await services.webhook_trigger(
            {"url": "https://api.example.com/hook", "method": "POST", "requester_id": "alice"}
        )
        assert "blocked for requester 'alice'" in result["content"][0]["text"].lower()
        _, details = audit_calls[-1]
        assert details["requester_id"] == "alice"
        assert details["requester_profile"] == "deny"
        assert "deny:user_profile" in details["decision_chain"]

    @pytest.mark.asyncio
    async def test_identity_user_control_cannot_override_global_home_readonly(self):
        from jarvis.config import Config
        from jarvis.tools import services

        cfg = Config()
        cfg.home_permission_profile = "readonly"
        cfg.identity_enforcement_enabled = True
        cfg.identity_user_profiles = {"owner": "control"}
        services.bind(cfg)

        result = await services.home_assistant_todo(
            {"action": "add", "entity_id": "todo.shopping", "item": "Milk", "requester_id": "owner"}
        )
        assert "readonly" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_identity_high_risk_webhook_requires_approval_code(self):
        from jarvis.config import Config
        from jarvis.tools import services

        cfg = Config()
        cfg.identity_enforcement_enabled = True
        cfg.identity_require_approval = True
        cfg.identity_approval_code = "super-secret-code"
        cfg.webhook_allowlist = ["example.com"]
        services.bind(cfg)

        denied = await services.webhook_trigger({"url": "https://api.example.com/hook", "method": "POST"})
        assert "requires approval" in denied["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_identity_high_risk_webhook_allows_code_or_trusted_approval(self):
        from jarvis.config import Config
        from jarvis.tools import services

        cfg = Config()
        cfg.identity_enforcement_enabled = True
        cfg.identity_require_approval = True
        cfg.identity_approval_code = "super-secret-code"
        cfg.identity_trusted_users = ["trusted-user"]
        cfg.webhook_allowlist = ["example.com"]
        services.bind(cfg)

        response = AsyncMock()
        response.status = 200
        response.text = AsyncMock(return_value="ok")
        context = AsyncMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.request = MagicMock(return_value=context)

        with patch("aiohttp.ClientSession", return_value=session):
            by_code = await services.webhook_trigger(
                {
                    "url": "https://api.example.com/hook",
                    "method": "POST",
                    "approval_code": "super-secret-code",
                    "requester_id": "guest-user",
                }
            )
            by_trusted = await services.webhook_trigger(
                {
                    "url": "https://api.example.com/hook",
                    "method": "POST",
                    "requester_id": "trusted-user",
                    "approved": True,
                }
            )

        assert "webhook delivered" in by_code["content"][0]["text"].lower()
        assert "webhook delivered" in by_trusted["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_dry_run_explicit_false_with_confirm(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools.services import smart_home

        # Sensitive domains require confirm=true when executing
        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "locked", "attributes": {}})
            post_resp = aiohttp_response(status=200)
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
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
    async def test_smart_home_sensitive_execute_requires_confirm(self, monkeypatch):
        from jarvis.tools import services

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        result = await services.smart_home({
            "domain": "lock",
            "action": "unlock",
            "entity_id": "lock.front_door",
            "dry_run": False,
        })
        assert "requires confirm=true" in result["content"][0]["text"].lower()
        _, details = audit_calls[-1]
        assert details["policy_decision"] == "denied"
        assert details["reason"] == "sensitive_confirm_required"

    @pytest.mark.asyncio
    async def test_smart_home_sensitive_execute_rejects_ambiguous_entity_target(self):
        from jarvis.tools import services

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.smart_home(
                {
                    "domain": "lock",
                    "action": "unlock",
                    "entity_id": "lock.all",
                    "dry_run": False,
                    "confirm": True,
                }
            )

        assert "ambiguous high-risk target" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_home_preview_only_returns_plan_preview(self):
        from jarvis.tools import services

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.smart_home(
                {
                    "domain": "light",
                    "action": "turn_on",
                    "entity_id": "light.preview_only",
                    "dry_run": False,
                    "preview_only": True,
                }
            )

        text = result["content"][0]["text"]
        assert "plan preview" in text.lower()
        assert "preview_token=" in text
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_home_strict_preview_ack_requires_token_then_executes(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.plan_preview_require_ack = True
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            gated = await services.smart_home(
                {
                    "domain": "light",
                    "action": "turn_on",
                    "entity_id": "light.preview_ack",
                    "dry_run": False,
                }
            )
        gated_text = gated["content"][0]["text"]
        assert "plan preview" in gated_text.lower()
        assert "preview_token=" in gated_text
        mock_session_cls.assert_not_called()

        preview_token = gated_text.split("preview_token=", 1)[1].split(" ", 1)[0].strip()
        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "off", "attributes": {}})
            post_resp = aiohttp_response(status=200)
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
            mock_session_cls.return_value = mock_session

            executed = await services.smart_home(
                {
                    "domain": "light",
                    "action": "turn_on",
                    "entity_id": "light.preview_ack",
                    "dry_run": False,
                    "preview_token": preview_token,
                }
            )

        assert "done:" in executed["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_climate_execute_requires_confirm(self):
        from jarvis.tools.services import smart_home

        result = await smart_home({
            "domain": "climate",
            "action": "set_hvac_mode",
            "entity_id": "climate.thermostat",
            "dry_run": False,
        })
        assert "requires confirm=true" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_rejects_unknown_domain_before_http(self):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await smart_home(
                {
                    "domain": "script",
                    "action": "turn_on",
                    "entity_id": "script.movie_mode",
                    "dry_run": True,
                }
            )

        assert "unsupported domain" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_home_normalizes_domain_action_entity_inputs(self):
        from jarvis.tools.services import smart_home

        result = await smart_home(
            {
                "domain": " Light ",
                "action": " Turn_On ",
                "entity_id": " LIGHT.KITCHEN ",
                "dry_run": True,
            }
        )
        assert "dry run" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", ["", " ", "turn on", "turn-on", "turn.on"])
    async def test_smart_home_rejects_invalid_action_format(self, action):
        from jarvis.tools.services import smart_home

        result = await smart_home(
            {
                "domain": "light",
                "action": action,
                "entity_id": "light.kitchen",
                "dry_run": True,
            }
        )
        assert "snake_case service name" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_smart_home_strict_confirm_mode_denies_unconfirmed_execute(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.home_require_confirm_execute = True
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.smart_home(
                {
                    "domain": "light",
                    "action": "turn_on",
                    "entity_id": "light.strict_mode",
                    "dry_run": False,
                }
            )

        assert "home_require_confirm_execute=true" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_home_strict_confirm_mode_allows_confirmed_execute(
        self, tmp_path, monkeypatch, aiohttp_response, aiohttp_session_mock
    ):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.home_require_confirm_execute = True
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "off", "attributes": {}})
            post_resp = aiohttp_response(status=200)
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
            mock_session_cls.return_value = mock_session

            result = await services.smart_home(
                {
                    "domain": "light",
                    "action": "turn_on",
                    "entity_id": "light.strict_mode_ok",
                    "dry_run": False,
                    "confirm": True,
                }
            )

        assert "done:" in result["content"][0]["text"].lower()
        _, details = audit_calls[-1]
        assert details["policy_decision"] == "allowed"

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
    async def test_smart_home_idempotent_turn_on_short_circuits(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "on", "attributes": {}})
            mock_session = aiohttp_session_mock(get=state_resp)
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
    async def test_smart_home_turn_off_unknown_state_executes(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "unknown", "attributes": {}})
            post_resp = aiohttp_response(status=200)
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
            mock_session_cls.return_value = mock_session

            result = await smart_home({
                "domain": "light",
                "action": "turn_off",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })

        assert "done:" in result["content"][0]["text"].lower()
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_smart_home_success_invalidates_cached_entity_state(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools import services

        services._ha_state_cache.clear()
        services._ha_state_cache["light.kitchen"] = (float("inf"), {"state": "off"})

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "off", "attributes": {}})
            post_resp = aiohttp_response(status=200)
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
            mock_session_cls.return_value = mock_session

            result = await services.smart_home({
                "domain": "light",
                "action": "turn_on",
                "entity_id": "light.kitchen",
                "dry_run": False,
            })

        assert "done:" in result["content"][0]["text"].lower()
        assert "light.kitchen" not in services._ha_state_cache

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
    async def test_smart_home_handles_error_body_read_failure(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools.services import smart_home

        with patch("aiohttp.ClientSession") as mock_session_cls:
            state_resp = aiohttp_response(status=200, json_data={"state": "off", "attributes": {}})
            post_resp = aiohttp_response(status=500, text_side_effect=RuntimeError("read failed"))
            mock_session = aiohttp_session_mock(get=state_resp, post=post_resp)
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
    async def test_smart_home_state_handles_invalid_json_response(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools.services import smart_home_state

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_side_effect=ValueError("bad json"))
            mock_session = aiohttp_session_mock(get=mock_resp)
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
    async def test_smart_home_state_normalizes_entity_id(self):
        from jarvis.tools import services

        with patch(
            "jarvis.tools.services._ha_get_state",
            new=AsyncMock(return_value=({"state": "on", "attributes": {}}, None)),
        ) as mock_get_state:
            result = await services.smart_home_state({"entity_id": " Light.Kitchen "})

        assert "state" in result["content"][0]["text"].lower()
        mock_get_state.assert_awaited_once_with("light.kitchen")

    @pytest.mark.asyncio
    async def test_smart_home_state_success_records_audit(self, monkeypatch, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools import services

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data={"state": "on", "attributes": {"friendly_name": "Kitchen"}})
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.smart_home_state({"entity_id": "light.kitchen"})

        assert "state" in result["content"][0]["text"].lower()
        action, details = audit_calls[-1]
        assert action == "smart_home_state"
        _assert_audit_payload(details, required={"result", "entity_id", "state"})
        assert details["result"] == "ok"
        assert details["entity_id"] == "light.kitchen"
        assert details["state"] == "on"

    @pytest.mark.asyncio
    async def test_smart_home_state_missing_entity_records_audit(self, monkeypatch):
        from jarvis.tools import services

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        result = await services.smart_home_state({})

        assert "entity id required" in result["content"][0]["text"].lower()
        action, details = audit_calls[-1]
        assert action == "smart_home_state"
        _assert_audit_payload(details, required={"result"})
        assert details["result"] == "missing_entity"

    @pytest.mark.asyncio
    async def test_home_assistant_capabilities_requires_entity_id(self):
        from jarvis.tools import services

        result = await services.home_assistant_capabilities({})
        assert "entity id required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_capabilities_success(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_state",
            AsyncMock(return_value=({"state": "on", "attributes": {"friendly_name": "Kitchen"}}, None)),
        )
        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_domain_services",
            AsyncMock(return_value=(["turn_on", "turn_off"], None)),
        )

        result = await services.home_assistant_capabilities({"entity_id": "light.kitchen"})
        payload = json.loads(result["content"][0]["text"])
        assert payload["entity_id"] == "light.kitchen"
        assert payload["state"] == "on"
        assert "turn_on" in payload["available_services"]
        assert "turn_off" in payload["available_services"]

    @pytest.mark.asyncio
    async def test_home_assistant_capabilities_not_found(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_state",
            AsyncMock(return_value=(None, "not_found")),
        )
        result = await services.home_assistant_capabilities({"entity_id": "light.missing"})
        assert "entity not found" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_capabilities_service_catalog_invalid_json(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_state",
            AsyncMock(return_value=({"state": "on", "attributes": {}}, None)),
        )
        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_domain_services",
            AsyncMock(return_value=(None, "invalid_json")),
        )
        result = await services.home_assistant_capabilities({"entity_id": "light.kitchen"})
        assert "invalid home assistant service catalog response" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_conversation_requires_feature_flag(self):
        from jarvis.tools import services

        result = await services.home_assistant_conversation({
            "text": "turn on kitchen lights",
            "confirm": True,
        })
        assert "disabled" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_conversation_requires_confirm(self):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "control"
        services.bind(cfg)

        result = await services.home_assistant_conversation({
            "text": "turn on kitchen lights",
        })
        assert "confirm=true" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_conversation_rejects_ambiguous_high_risk_text(self):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "control"
        services.bind(cfg)

        result = await services.home_assistant_conversation(
            {
                "text": "unlock it now",
                "confirm": True,
            }
        )
        assert "ambiguous" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_conversation_denies_readonly_profile(self):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "readonly"
        services.bind(cfg)

        result = await services.home_assistant_conversation({
            "text": "turn on kitchen lights",
            "confirm": True,
        })
        assert "home_conversation_permission_profile=control" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_conversation_success(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "control"
        services.bind(cfg)

        response = aiohttp_response(
            status=200,
            json_data={
                "response": {
                    "response_type": "action_done",
                    "speech": {"plain": {"speech": "Done."}},
                },
                "conversation_id": "abc123",
            },
        )
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value = aiohttp_session_mock(post=response)
            result = await services.home_assistant_conversation({
                "text": "turn off the kitchen lights",
                "confirm": True,
                "language": "en",
            })

        text = result["content"][0]["text"]
        assert "done." in text.lower()
        assert "type=action_done" in text
        assert "conversation_id=abc123" in text

    @pytest.mark.asyncio
    async def test_home_assistant_conversation_invalid_json(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "control"
        services.bind(cfg)

        response = aiohttp_response(status=200, json_data="not-a-dict")
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value = aiohttp_session_mock(post=response)
            result = await services.home_assistant_conversation({
                "text": "turn off the kitchen lights",
                "confirm": True,
            })
        assert "invalid home assistant conversation response" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "expected_text", "expected_detail"),
        [
            (401, "authentication failed", "auth"),
            (404, "endpoint not found", "not_found"),
            (500, "conversation error (500)", "http_error"),
        ],
    )
    async def test_home_assistant_conversation_http_mappings(
        self,
        status,
        expected_text,
        expected_detail,
        aiohttp_response,
        aiohttp_session_mock,
    ):
        from jarvis.tools import services
        from jarvis.tool_summary import list_summaries

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "control"
        services.bind(cfg)

        response = aiohttp_response(status=status, json_data={})
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value = aiohttp_session_mock(post=response)
            result = await services.home_assistant_conversation({
                "text": "turn off the kitchen lights",
                "confirm": True,
            })
        assert expected_text in result["content"][0]["text"].lower()
        summaries = list_summaries(25)
        assert any(
            item.get("name") == "home_assistant_conversation" and item.get("detail") == expected_detail
            for item in summaries
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("side_effect", "expected_text", "expected_detail"),
        [
            (asyncio.TimeoutError(), "timed out", "timeout"),
            (asyncio.CancelledError(), "was cancelled", "cancelled"),
            (aiohttp.ClientError("boom"), "failed to reach", "network_client_error"),
        ],
    )
    async def test_home_assistant_conversation_transport_error_mappings(
        self,
        side_effect,
        expected_text,
        expected_detail,
    ):
        from jarvis.tools import services
        from jarvis.tool_summary import list_summaries

        cfg = services._config
        assert cfg is not None
        cfg.home_conversation_enabled = True
        cfg.home_conversation_permission_profile = "control"
        services.bind(cfg)

        with patch("aiohttp.ClientSession", side_effect=side_effect):
            result = await services.home_assistant_conversation({
                "text": "turn off the kitchen lights",
                "confirm": True,
            })
        assert expected_text in result["content"][0]["text"].lower()
        summaries = list_summaries(25)
        assert any(
            item.get("name") == "home_assistant_conversation" and item.get("detail") == expected_detail
            for item in summaries
        )

    @pytest.mark.asyncio
    async def test_home_assistant_todo_list_success(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._ha_call_service",
            AsyncMock(
                return_value=(
                    [
                        {
                            "service_response": {
                                "todo.shopping": {
                                    "items": [
                                        {"summary": "Milk", "uid": "a1", "status": "needs_action"},
                                        {"summary": "Eggs", "uid": "a2", "status": "completed"},
                                    ]
                                }
                            }
                        }
                    ],
                    None,
                )
            ),
        )

        result = await services.home_assistant_todo({"action": "list", "entity_id": "todo.shopping"})
        text = result["content"][0]["text"].lower()
        assert "milk" in text
        assert "eggs" in text
        assert "id=a1" in text

    @pytest.mark.asyncio
    async def test_home_assistant_todo_readonly_denies_add(self):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.home_permission_profile = "readonly"
        services.bind(cfg)

        result = await services.home_assistant_todo(
            {"action": "add", "entity_id": "todo.shopping", "item": "Milk"}
        )
        assert "readonly" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_timer_state_success(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_state",
            AsyncMock(
                return_value=(
                    {
                        "state": "active",
                        "attributes": {"remaining": "0:04:00", "duration": "0:05:00", "finishes_at": "2026-01-01T00:00:00+00:00"},
                    },
                    None,
                )
            ),
        )

        result = await services.home_assistant_timer({"action": "state", "entity_id": "timer.kitchen"})
        payload = json.loads(result["content"][0]["text"])
        assert payload["state"] == "active"
        assert payload["remaining"] == "0:04:00"

    @pytest.mark.asyncio
    async def test_home_assistant_timer_start_invalid_duration(self):
        from jarvis.tools import services

        result = await services.home_assistant_timer(
            {"action": "start", "entity_id": "timer.kitchen", "duration": "soon"}
        )
        assert "hh:mm:ss" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_home_assistant_area_entities_success(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._ha_render_template",
            AsyncMock(return_value=("light.kitchen\nswitch.coffee\nlight.table\n", None)),
        )
        monkeypatch.setattr(
            "jarvis.tools.services._ha_get_state",
            AsyncMock(
                side_effect=[
                    ({"state": "on", "attributes": {"friendly_name": "Kitchen"}}, None),
                    ({"state": "off", "attributes": {"friendly_name": "Table"}}, None),
                ]
            ),
        )

        result = await services.home_assistant_area_entities(
            {"area": "Kitchen", "domain": "light", "include_states": True}
        )
        payload = json.loads(result["content"][0]["text"])
        assert payload["area"] == "Kitchen"
        assert payload["entities"] == ["light.kitchen", "light.table"]
        assert len(payload["states"]) == 2

    @pytest.mark.asyncio
    async def test_media_control_dry_run(self):
        from jarvis.tools import services

        result = await services.media_control(
            {"entity_id": "media_player.office", "action": "play", "dry_run": True}
        )
        assert "dry run" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_weather_lookup_success(self, aiohttp_response, aiohttp_session_mock):
        from jarvis.tools import services

        geocode_resp = aiohttp_response(
            status=200,
            json_data={
                "results": [
                    {
                        "name": "San Francisco",
                        "country": "United States",
                        "latitude": 37.77,
                        "longitude": -122.42,
                    }
                ]
            },
        )
        forecast_resp = aiohttp_response(
            status=200,
            json_data={
                "current": {
                    "temperature_2m": 64,
                    "apparent_temperature": 62,
                    "relative_humidity_2m": 55,
                    "weather_code": 2,
                    "wind_speed_10m": 10,
                }
            },
        )
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value = aiohttp_session_mock(get=[geocode_resp, forecast_resp])
            result = await services.weather_lookup({"location": "San Francisco"})
        text = result["content"][0]["text"].lower()
        assert "san francisco" in text
        assert "partly cloudy" in text

    @pytest.mark.asyncio
    async def test_webhook_trigger_enforces_allowlist(self):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.webhook_allowlist = ["example.com"]
        services.bind(cfg)
        result = await services.webhook_trigger({"url": "https://malicious.test/hook"})
        assert "allowlist" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_webhook_trigger_success_injects_auth_token(self):
        from jarvis.tools import services

        cfg = services._config
        assert cfg is not None
        cfg.webhook_allowlist = ["example.com"]
        cfg.webhook_auth_token = "secret-token"
        services.bind(cfg)

        response = AsyncMock()
        response.status = 200
        response.text = AsyncMock(return_value="ok")
        context = AsyncMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.request = MagicMock(return_value=context)

        with patch("aiohttp.ClientSession", return_value=session):
            result = await services.webhook_trigger(
                {"url": "https://api.example.com/hooks/jarvis", "method": "POST", "payload": {"ok": True}}
            )
        assert "webhook delivered" in result["content"][0]["text"].lower()
        call_headers = session.request.call_args.kwargs["headers"]
        assert call_headers["Authorization"] == "Bearer secret-token"

    @pytest.mark.asyncio
    async def test_webhook_inbound_list_and_clear(self):
        from jarvis.tools import services

        services._inbound_webhook_events.clear()
        services.record_inbound_webhook_event(
            payload={"event": "doorbell"},
            headers={"x-test": "1"},
            source="ha",
            path="/api/webhook/inbound",
        )
        listed = await services.webhook_inbound_list({"limit": 10})
        payload = json.loads(listed["content"][0]["text"])
        assert payload
        assert payload[0]["source"] == "ha"

        cleared = await services.webhook_inbound_clear({})
        assert "cleared inbound webhook events" in cleared["content"][0]["text"].lower()
        empty = await services.webhook_inbound_list({"limit": 10})
        assert json.loads(empty["content"][0]["text"]) == []

    @pytest.mark.asyncio
    async def test_reminder_create_list_complete_lifecycle(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        created = await services.reminder_create({"text": "Stretch", "due": "10m"})
        created_text = created["content"][0]["text"]
        reminder_id = int(created_text.split()[1])
        assert "reminder" in created_text.lower()

        listed = await services.reminder_list({})
        assert "stretch" in listed["content"][0]["text"].lower()

        completed = await services.reminder_complete({"reminder_id": reminder_id})
        assert f"completed reminder {reminder_id}" in completed["content"][0]["text"].lower()

        completed_list = await services.reminder_list({"include_completed": True})
        assert "completed at" in completed_list["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_reminder_create_rejects_past_due_timestamp(self):
        from jarvis.tools import services

        result = await services.reminder_create({"text": "Past", "due": "2001-01-01T00:00:00Z"})
        assert "future" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_reminder_notify_due_dispatches_and_marks_notified(self, tmp_path, monkeypatch):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.pushover_api_token = "token"
        cfg.pushover_user_key = "user"
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        reminder_id = store.add_reminder(text="Take break", due_at=time.time() - 30.0, created_at=time.time() - 60.0)
        services._reminders[reminder_id] = {
            "id": reminder_id,
            "text": "Take break",
            "due_at": time.time() - 30.0,
            "created_at": time.time() - 60.0,
            "status": "pending",
            "completed_at": None,
            "notified_at": None,
        }

        async def _fake_notify(args):
            return {"content": [{"type": "text", "text": "Notification sent."}]}

        monkeypatch.setattr("jarvis.tools.services.pushover_notify", _fake_notify)
        result = await services.reminder_notify_due({"limit": 5})
        assert "sent: 1" in result["content"][0]["text"].lower()

        rows = store.list_reminders(status="pending", include_notified=False)
        assert rows == []

    @pytest.mark.asyncio
    async def test_reminder_notify_due_defers_inside_quiet_window(self, tmp_path, monkeypatch):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.pushover_api_token = "token"
        cfg.pushover_user_key = "user"
        cfg.nudge_policy = "defer"
        now_local = time.localtime()
        now_minutes = (now_local.tm_hour * 60) + now_local.tm_min
        start_minutes = (now_minutes - 1) % (24 * 60)
        end_minutes = (now_minutes + 1) % (24 * 60)
        cfg.nudge_quiet_hours_start = f"{start_minutes // 60:02d}:{start_minutes % 60:02d}"
        cfg.nudge_quiet_hours_end = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"

        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        reminder_id = store.add_reminder(text="Water plants", due_at=time.time() - 10.0, created_at=time.time() - 120.0)
        services._reminders[reminder_id] = {
            "id": reminder_id,
            "text": "Water plants",
            "due_at": time.time() - 10.0,
            "created_at": time.time() - 120.0,
            "status": "pending",
            "completed_at": None,
            "notified_at": None,
        }

        notify_calls: list[dict] = []

        async def _fake_notify(args):
            notify_calls.append(dict(args))
            return {"content": [{"type": "text", "text": "Notification sent."}]}

        monkeypatch.setattr("jarvis.tools.services.pushover_notify", _fake_notify)
        result = await services.reminder_notify_due({"limit": 5})
        text = result["content"][0]["text"].lower()
        assert "deferred 1 due reminder notifications" in text
        assert notify_calls == []

    @pytest.mark.asyncio
    async def test_calendar_events_success(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._calendar_fetch_events",
            AsyncMock(
                return_value=(
                    [
                        {
                            "summary": "Standup",
                            "entity_id": "calendar.work",
                            "location": "Office",
                            "start_ts": time.time() + 300.0,
                            "all_day": False,
                        }
                    ],
                    None,
                )
            ),
        )
        result = await services.calendar_events({"window_hours": 4})
        text = result["content"][0]["text"].lower()
        assert "standup" in text
        assert "calendar.work" in text

    @pytest.mark.asyncio
    async def test_calendar_next_event_empty(self, monkeypatch):
        from jarvis.tools import services

        monkeypatch.setattr(
            "jarvis.tools.services._calendar_fetch_events",
            AsyncMock(return_value=([], None)),
        )
        result = await services.calendar_next_event({})
        assert "no upcoming calendar events" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_calendar_events_invalid_window_rejected(self):
        from jarvis.tools import services

        result = await services.calendar_events({"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"})
        assert "invalid calendar window" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_timer_create_list_cancel_lifecycle(self):
        from jarvis.tools import services

        created = await services.timer_create({"duration": "5m", "label": "tea"})
        created_text = created["content"][0]["text"]
        assert "timer" in created_text.lower()

        listed = await services.timer_list({})
        listed_text = listed["content"][0]["text"]
        assert "tea" in listed_text.lower()
        assert "- " in listed_text

        timer_id = int(created_text.split()[1])
        cancelled = await services.timer_cancel({"timer_id": timer_id})
        assert f"cancelled timer {timer_id}" in cancelled["content"][0]["text"].lower()

        empty = await services.timer_list({})
        assert "no active timers" in empty["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_timer_create_rejects_invalid_duration(self):
        from jarvis.tools import services

        result = await services.timer_create({"duration": "soon"})
        assert "duration is required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_timer_cancel_by_label(self):
        from jarvis.tools import services

        await services.timer_create({"duration": 120, "label": "stretch"})
        result = await services.timer_cancel({"label": "stretch"})
        assert "cancelled timer" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_timer_list_include_expired(self):
        from jarvis.tools import services

        created = await services.timer_create({"duration": 60, "label": "expired-sample"})
        timer_id = int(created["content"][0]["text"].split()[1])
        services._timers[timer_id]["due_mono"] = time.monotonic() - 5.0

        shown = await services.timer_list({"include_expired": True})
        assert "expired" in shown["content"][0]["text"].lower()

        hidden = await services.timer_list({})
        assert "no active timers" in hidden["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_timer_persists_across_bind(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        created = await services.timer_create({"duration": 600, "label": "persisted"})
        timer_id = int(created["content"][0]["text"].split()[1])

        services.bind(cfg, store)
        listed = await services.timer_list({})
        text = listed["content"][0]["text"].lower()
        assert "persisted" in text
        assert f"- {timer_id}" in text

    @pytest.mark.asyncio
    async def test_timer_cancel_persists_across_bind(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        created = await services.timer_create({"duration": 600, "label": "to-cancel"})
        timer_id = int(created["content"][0]["text"].split()[1])
        await services.timer_cancel({"timer_id": timer_id})

        services.bind(cfg, store)
        listed = await services.timer_list({})
        assert "no active timers" in listed["content"][0]["text"].lower()

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
    async def test_slack_notify_requires_config(self):
        from jarvis.tools import services

        result = await services.slack_notify({"message": "hello"})
        assert "slack webhook not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_discord_notify_requires_config(self):
        from jarvis.tools import services

        result = await services.discord_notify({"message": "hello"})
        assert "discord webhook not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_email_send_requires_config(self):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.email_permission_profile = "control"
        store = MemoryStore(":memory:")
        services.bind(cfg, store)
        result = await services.email_send({"subject": "Test", "body": "Body", "confirm": True})
        assert "email not configured" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_add_task_success(self, tmp_path, aiohttp_response, aiohttp_session_mock):
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
            mock_resp = aiohttp_response(status=200, json_data={"id": "123"})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_add_task({"content": "Buy coffee"})

        assert "created" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_add_task_invalid_json_response(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_side_effect=ValueError("bad json"))
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_add_task({"content": "Buy coffee"})

        assert "invalid todoist response" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_todoist_add_task_unexpected_error_hides_exception_details(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession", side_effect=RuntimeError("secret token leak")):
            result = await services.todoist_add_task({"content": "Buy coffee"})

        text = result["content"][0]["text"]
        assert "unexpected todoist error" in text.lower()
        assert "secret token leak" not in text.lower()

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_invalid_json_records_audit(
        self,
        tmp_path,
        monkeypatch,
        aiohttp_response,
        aiohttp_session_mock,
    ):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_side_effect=ValueError("bad json"))
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_list_tasks({"limit": 1})

        assert "invalid todoist response" in result["content"][0]["text"].lower()
        action, details = audit_calls[-1]
        assert action == "todoist_list_tasks"
        _assert_audit_payload(details, required={"result"})
        assert details["result"] == "invalid_json"

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_unexpected_error_hides_exception_details(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession", side_effect=RuntimeError("secret token leak")):
            result = await services.todoist_list_tasks({"limit": 1})

        text = result["content"][0]["text"]
        assert "unexpected todoist error" in text.lower()
        assert "secret token leak" not in text.lower()

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_non_list_payload_records_audit(
        self,
        tmp_path,
        monkeypatch,
        aiohttp_response,
        aiohttp_session_mock,
    ):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data={"content": "Buy coffee"})
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_list_tasks({"limit": 1})

        assert "invalid todoist response" in result["content"][0]["text"].lower()
        action, details = audit_calls[-1]
        assert action == "todoist_list_tasks"
        _assert_audit_payload(details, required={"result"})
        assert details["result"] == "invalid_json"

    def test_retry_backoff_delay_bounds_and_jitter(self):
        from jarvis.tools import services

        delay_low = services._retry_backoff_delay(0, jitter_sample=0.0)
        delay_mid = services._retry_backoff_delay(0, jitter_sample=0.5)
        delay_high = services._retry_backoff_delay(0, jitter_sample=1.0)
        delay_capped = services._retry_backoff_delay(10, jitter_sample=0.5)

        assert 0.0 <= delay_low <= delay_mid <= delay_high
        assert delay_capped <= services.RETRY_MAX_DELAY_SEC

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_retries_timeout_then_succeeds(self, tmp_path, monkeypatch, aiohttp_response):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        timeout_ctx = AsyncMock()
        timeout_ctx.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)
        timeout_ctx.__aexit__ = AsyncMock(return_value=False)

        success_resp = aiohttp_response(status=200, json_data=[{"content": "Buy coffee"}])
        success_ctx = AsyncMock()
        success_ctx.__aenter__ = AsyncMock(return_value=success_resp)
        success_ctx.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(side_effect=[timeout_ctx, success_ctx])

        sleep_calls: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("jarvis.tools.services.asyncio.sleep", _fake_sleep)
        with patch("aiohttp.ClientSession", return_value=session):
            result = await services.todoist_list_tasks({"limit": 1})

        assert "buy coffee" in result["content"][0]["text"].lower()
        assert len(sleep_calls) == 1
        assert session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_todoist_add_task_rejects_invalid_labels_type(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.todoist_add_task({"content": "Buy coffee", "labels": "personal"})

        assert "labels must be a list" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_todoist_add_task_rejects_invalid_labels_entries(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.todoist_add_task({"content": "Buy coffee", "labels": ["ok", ""]})

        assert "labels must be a list" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_todoist_add_task_rejects_invalid_priority(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.todoist_add_task({"content": "Buy coffee", "priority": 99})

        assert "priority must be an integer between 1 and 4" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_success(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data=[{"content": "Buy coffee"}, {"content": "Call mom"}])
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_list_tasks({"limit": 2})

        text = result["content"][0]["text"].lower()
        assert "buy coffee" in text
        assert "call mom" in text

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_verbose_format(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(
                status=200,
                json_data=[
                    {
                        "id": "t-1",
                        "content": "Buy coffee",
                        "priority": 4,
                        "labels": ["errands", "home"],
                        "due": {"string": "tomorrow morning"},
                    }
                ],
            )
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_list_tasks({"limit": 1, "format": "verbose"})

        text = result["content"][0]["text"].lower()
        assert "buy coffee" in text
        assert "id=t-1" in text
        assert "p=4" in text
        assert "due=tomorrow morning" in text
        assert "labels=errands,home" in text

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_rejects_invalid_format(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            result = await services.todoist_list_tasks({"format": "detailed"})

        assert "format must be 'short' or 'verbose'" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_uses_configured_timeout(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.todoist_timeout_sec = 3.5
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data=[{"content": "Buy coffee"}])
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            await services.todoist_list_tasks({"limit": 1})

        timeout_arg = mock_session_cls.call_args.kwargs["timeout"]
        assert timeout_arg.total == 3.5

    @pytest.mark.asyncio
    async def test_todoist_timeout_is_capped_by_turn_act_budget(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.todoist_timeout_sec = 9.0
        cfg.turn_timeout_act_sec = 2.0
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data=[{"content": "Buy coffee"}])
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            await services.todoist_list_tasks({"limit": 1})

        timeout_arg = mock_session_cls.call_args.kwargs["timeout"]
        assert timeout_arg.total == 2.0

    @pytest.mark.asyncio
    async def test_todoist_list_tasks_rejects_non_object_entries(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data=[{"content": "Buy coffee"}, "bad-item"])
            mock_session = aiohttp_session_mock(get=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.todoist_list_tasks({"limit": 5})

        assert "invalid todoist response" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_pushover_notify_success(self, tmp_path, aiohttp_response, aiohttp_session_mock):
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
            mock_resp = aiohttp_response(status=200, json_data={"status": 1})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.pushover_notify({"message": "hello"})

        assert "sent" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_slack_notify_success(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.slack_webhook_url = "https://hooks.slack.test/abc"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data={"ok": True})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.slack_notify({"message": "hello"})

        assert "slack notification sent" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_discord_notify_success(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.discord_webhook_url = "https://discord.test/api/webhooks/abc"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=204, json_data={})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.discord_notify({"message": "hello"})

        assert "discord notification sent" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_email_send_requires_confirm(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.email_permission_profile = "control"
        cfg.email_smtp_host = "smtp.example.com"
        cfg.email_from = "jarvis@example.com"
        cfg.email_default_to = "owner@example.com"
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        result = await services.email_send({"subject": "Test", "body": "Body"})
        assert "confirm=true" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_email_send_and_summary_success(self, tmp_path, monkeypatch):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.email_permission_profile = "control"
        cfg.email_smtp_host = "smtp.example.com"
        cfg.email_from = "jarvis@example.com"
        cfg.email_default_to = "owner@example.com"
        store = MemoryStore(str(tmp_path / "memory.sqlite"))
        services.bind(cfg, store)

        sent_messages: list[tuple[str, str]] = []

        def _fake_send(*, recipient: str, subject: str, body: str) -> None:
            sent_messages.append((recipient, subject))

        monkeypatch.setattr("jarvis.tools.services._send_email_sync", _fake_send)
        sent = await services.email_send({"subject": "Status", "body": "All good", "confirm": True})
        assert "email sent to owner@example.com" in sent["content"][0]["text"].lower()
        assert sent_messages == [("owner@example.com", "Status")]

        summary = await services.email_summary({"limit": 5})
        assert "email sent to owner@example.com: status" in summary["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_pushover_notify_rejects_invalid_priority(self, tmp_path):
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
            result = await services.pushover_notify({"message": "hello", "priority": 9})

        assert "priority must be an integer between -2 and 2" in result["content"][0]["text"].lower()
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_pushover_notify_unexpected_error_hides_exception_details(self, tmp_path):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession", side_effect=RuntimeError("secret token leak")):
            result = await services.pushover_notify({"message": "hello"})

        text = result["content"][0]["text"]
        assert "unexpected pushover error" in text.lower()
        assert "secret token leak" not in text.lower()

    @pytest.mark.asyncio
    async def test_pushover_notify_uses_configured_timeout(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        cfg.pushover_timeout_sec = 4.25
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data={"status": 1})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            await services.pushover_notify({"message": "hello"})

        timeout_arg = mock_session_cls.call_args.kwargs["timeout"]
        assert timeout_arg.total == 4.25

    @pytest.mark.asyncio
    async def test_pushover_notify_api_reject_with_error_list(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services
        from jarvis.tool_summary import list_summaries

        cfg = Config()
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data={"status": 0, "errors": ["user identifier is invalid"]})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.pushover_notify({"message": "hello"})

        assert "rejected" in result["content"][0]["text"].lower()
        summaries = list_summaries(20)
        assert any(item.get("name") == "pushover_notify" and item.get("detail") == "api_error" for item in summaries)

    @pytest.mark.asyncio
    async def test_pushover_notify_invalid_status_type_is_invalid_json(self, tmp_path, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services
        from jarvis.tool_summary import list_summaries

        cfg = Config()
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = aiohttp_response(status=200, json_data={"status": "ok"})
            mock_session = aiohttp_session_mock(post=mock_resp)
            mock_session_cls.return_value = mock_session

            result = await services.pushover_notify({"message": "hello"})

        assert "invalid pushover response" in result["content"][0]["text"].lower()
        summaries = list_summaries(20)
        assert any(item.get("name") == "pushover_notify" and item.get("detail") == "invalid_json" for item in summaries)

    @pytest.mark.asyncio
    @pytest.mark.fault
    @pytest.mark.parametrize(
        ("tool_name", "args", "method"),
        [
            ("todoist_add_task", {"content": "Buy coffee"}, "post"),
            ("todoist_list_tasks", {"limit": 1}, "get"),
            ("pushover_notify", {"message": "hello"}, "post"),
        ],
    )
    @pytest.mark.parametrize(
        ("exc", "message_fragment"),
        [
            (asyncio.TimeoutError(), "timed out"),
            (asyncio.CancelledError(), "was cancelled"),
            (aiohttp.ClientError("boom"), "failed to reach"),
        ],
    )
    async def test_integration_transport_error_paths_are_parameterized(
        self, tmp_path, monkeypatch, tool_name, args, method, exc, message_fragment
    ):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        async def _no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr("jarvis.tools.services.asyncio.sleep", _no_sleep)

        error_ctx = AsyncMock()
        error_ctx.__aenter__ = AsyncMock(side_effect=exc)
        error_ctx.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=error_ctx)
        session.post = MagicMock(return_value=error_ctx)

        with patch("aiohttp.ClientSession", return_value=session):
            result = await getattr(services, tool_name)(args)

        text = result["content"][0]["text"].lower()
        assert message_fragment in text

    @pytest.mark.asyncio
    async def test_todoist_and_pushover_tools_audit_on_success(self, tmp_path, monkeypatch, aiohttp_response, aiohttp_session_mock):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_post_resp = aiohttp_response(status=200, json_data={"id": "a1"})
            mock_notify_resp = aiohttp_response(status=200, json_data={"status": 1})
            mock_session = aiohttp_session_mock(post=[mock_post_resp, mock_notify_resp])
            mock_session_cls.return_value = mock_session

            await services.todoist_add_task({"content": "Buy coffee"})
            await services.pushover_notify({"message": "hello"})

        actions = [name for name, _ in audit_calls]
        assert "todoist_add_task" in actions
        assert "pushover_notify" in actions

    @pytest.mark.asyncio
    async def test_todoist_and_pushover_audit_does_not_log_raw_content(
        self, tmp_path, monkeypatch, aiohttp_response, aiohttp_session_mock
    ):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        audit_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr("jarvis.tools.services._audit", lambda action, details: audit_calls.append((action, details)))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_add_resp = aiohttp_response(status=200, json_data={"id": "t1"})
            mock_notify_resp = aiohttp_response(status=200, json_data={"status": 1})
            mock_session = aiohttp_session_mock(post=[mock_add_resp, mock_notify_resp])
            mock_session_cls.return_value = mock_session

            await services.todoist_add_task({"content": "my password is swordfish"})
            await services.pushover_notify({"message": "otp 123456"})

        by_action = {name: details for name, details in audit_calls}
        _assert_audit_payload(by_action["todoist_add_task"], forbidden={"content_preview"})
        _assert_audit_payload(by_action["pushover_notify"], forbidden={"message_preview", "title"})
        assert by_action["todoist_add_task"]["content_length"] == len("my password is swordfish")
        assert by_action["pushover_notify"]["message_length"] == len("otp 123456")
        assert by_action["pushover_notify"]["title_length"] == len("Jarvis")

    @pytest.mark.asyncio
    async def test_todoist_and_pushover_audit_log_entries_are_metadata_only(
        self, tmp_path, aiohttp_response, aiohttp_session_mock
    ):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.todoist_api_token = "todo-token"
        cfg.pushover_api_token = "app-token"
        cfg.pushover_user_key = "user-key"
        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_add_resp = aiohttp_response(status=200, json_data={"id": "t1"})
            mock_notify_resp = aiohttp_response(status=200, json_data={"status": 1})
            mock_session = aiohttp_session_mock(post=[mock_add_resp, mock_notify_resp])
            mock_session_cls.return_value = mock_session

            await services.todoist_add_task(
                {
                    "content": "my password is swordfish",
                    "description": "raw details",
                    "due_string": "tomorrow",
                }
            )
            await services.pushover_notify({"message": "otp 123456", "title": "Bank code"})

        entries = [json.loads(line) for line in services.AUDIT_LOG.read_text().splitlines() if line.strip()]
        todoist_entry = next(
            entry for entry in entries if entry.get("action") == "todoist_add_task" and entry.get("result") == "ok"
        )
        pushover_entry = next(
            entry for entry in entries if entry.get("action") == "pushover_notify" and entry.get("result") == "ok"
        )

        for forbidden in {"content", "description", "due_string", "message", "title"}:
            _assert_audit_payload(todoist_entry, forbidden={forbidden})
            _assert_audit_payload(pushover_entry, forbidden={forbidden})

        assert todoist_entry["content_length"] == len("my password is swordfish")
        assert pushover_entry["message_length"] == len("otp 123456")
        assert pushover_entry["title_length"] == len("Bank code")

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
    async def test_memory_search_uses_config_defaults_when_args_missing(self, tmp_path, monkeypatch):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.memory_max_sensitivity = 0.2
        cfg.memory_hybrid_weight = 0.33
        cfg.memory_decay_enabled = True
        cfg.memory_decay_half_life_days = 9.0
        cfg.memory_mmr_enabled = True
        cfg.memory_mmr_lambda = 0.55

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        captured: dict[str, object] = {}

        def wrapped_search_v2(query: str, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(store, "search_v2", wrapped_search_v2)

        result = await services.memory_search({"query": "hello"})

        assert "no relevant" in result["content"][0]["text"].lower()
        assert captured["max_sensitivity"] == 0.2
        assert captured["hybrid_weight"] == 0.33
        assert captured["decay_enabled"] is True
        assert captured["decay_half_life_days"] == 9.0
        assert captured["mmr_enabled"] is True
        assert captured["mmr_lambda"] == 0.55

    @pytest.mark.asyncio
    async def test_memory_search_include_sensitive_overrides_config_sensitivity(self, tmp_path, monkeypatch):
        from jarvis.config import Config
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = Config()
        cfg.memory_max_sensitivity = 0.1
        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(cfg, store)

        captured: dict[str, object] = {}

        def wrapped_search_v2(query: str, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(store, "search_v2", wrapped_search_v2)

        await services.memory_search({"query": "hello", "include_sensitive": True})

        assert captured["max_sensitivity"] is None

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
    async def test_task_plan_update_accepts_case_insensitive_status(self, tmp_path):
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        memory_path = tmp_path / "memory.sqlite"
        store = MemoryStore(str(memory_path))
        services.bind(services._config, store)

        await services.task_plan_create({"title": "Plan", "steps": ["step"]})
        result = await services.task_plan_update({"plan_id": 1, "step_index": 0, "status": "DONE"})
        assert "updated" in result["content"][0]["text"].lower()

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
        assert payload["schema_version"] == "1.3"
        assert "local_time" in payload
        assert "tool_policy" in payload
        assert isinstance(payload["tool_policy"]["home_require_confirm_execute"], bool)
        assert isinstance(payload["tool_policy"]["home_conversation_enabled"], bool)
        assert isinstance(payload["tool_policy"]["memory_pii_guardrails_enabled"], bool)
        assert payload["tool_policy"]["home_conversation_permission_profile"] in {"readonly", "control"}
        assert payload["tool_policy"]["email_permission_profile"] in {"readonly", "control"}
        assert isinstance(payload["tool_policy"]["identity_enforcement_enabled"], bool)
        assert payload["tool_policy"]["identity_default_profile"] in {"deny", "readonly", "control", "trusted"}
        assert isinstance(payload["tool_policy"]["identity_require_approval"], bool)
        assert isinstance(payload["tool_policy"]["plan_preview_require_ack"], bool)
        assert isinstance(payload["tool_policy"]["safe_mode_enabled"], bool)
        assert payload["tool_policy"]["nudge_policy"] in {"interrupt", "defer", "adaptive"}
        assert "nudge_quiet_hours_start" in payload["tool_policy"]
        assert "nudge_quiet_hours_end" in payload["tool_policy"]
        assert isinstance(payload["tool_policy"]["nudge_quiet_window_active"], bool)
        assert "memory" in payload
        assert "audit" in payload
        assert payload["audit"]["redaction_enabled"] is True
        assert payload["audit"]["redaction_key_count"] >= 1
        assert "todoist_add_task" in payload["audit"]["metadata_only_actions"]
        assert "todoist_configured" in payload
        assert "pushover_configured" in payload
        assert "timers" in payload
        assert "active_count" in payload["timers"]
        assert "reminders" in payload
        assert "pending_count" in payload["reminders"]
        assert "voice_attention" in payload
        assert "mode" in payload["voice_attention"]
        assert "active_room" in payload["voice_attention"]
        assert "turn_choreography" in payload["voice_attention"]
        assert "phase" in payload["voice_attention"]["turn_choreography"]
        assert "turn_timeouts" in payload
        assert isinstance(payload["turn_timeouts"]["watchdog_enabled"], bool)
        assert payload["turn_timeouts"]["listen_sec"] > 0
        assert payload["turn_timeouts"]["think_sec"] > 0
        assert payload["turn_timeouts"]["speak_sec"] > 0
        assert payload["turn_timeouts"]["act_sec"] > 0
        assert "integrations" in payload
        assert "weather" in payload["integrations"]
        assert "webhook" in payload["integrations"]
        assert "email" in payload["integrations"]
        assert "channels" in payload["integrations"]
        assert "identity" in payload
        assert isinstance(payload["identity"]["enabled"], bool)
        assert isinstance(payload["identity"]["trusted_user_count"], int)
        assert isinstance(payload["identity"]["user_profiles"], dict)
        assert "plan_preview" in payload
        assert isinstance(payload["plan_preview"]["pending_count"], int)
        assert payload["plan_preview"]["ttl_sec"] > 0
        assert isinstance(payload["plan_preview"]["strict_mode"], bool)
        assert "skills" in payload
        assert "observability" in payload
        assert "intent_metrics" in payload["observability"]
        assert "correction_frequency" in payload["observability"]["intent_metrics"]
        assert "retention_policy" in payload
        assert "memory_retention_days" in payload["retention_policy"]
        assert payload["health"]["health_level"] in {"ok", "degraded", "error"}

    @pytest.mark.asyncio
    async def test_system_status_contract_reports_expected_fields(self):
        from jarvis.tools import services

        result = await services.system_status_contract({})
        payload = json.loads(result["content"][0]["text"])
        assert payload["schema_version"] == "1.3"
        assert "top_level_required" in payload
        assert "tool_policy" in payload["top_level_required"]
        assert "identity" in payload["top_level_required"]
        assert "voice_attention" in payload["top_level_required"]
        assert "turn_timeouts" in payload["top_level_required"]
        assert "skills" in payload["top_level_required"]
        assert "observability" in payload["top_level_required"]
        assert "plan_preview" in payload["top_level_required"]
        assert "tool_policy_required" in payload
        assert "home_conversation_permission_profile" in payload["tool_policy_required"]
        assert "email_permission_profile" in payload["tool_policy_required"]
        assert "memory_pii_guardrails_enabled" in payload["tool_policy_required"]
        assert "safe_mode_enabled" in payload["tool_policy_required"]
        assert "identity_enforcement_enabled" in payload["tool_policy_required"]
        assert "identity_default_profile" in payload["tool_policy_required"]
        assert "identity_require_approval" in payload["tool_policy_required"]
        assert "plan_preview_require_ack" in payload["tool_policy_required"]
        assert "nudge_policy" in payload["tool_policy_required"]
        assert "nudge_quiet_hours_start" in payload["tool_policy_required"]
        assert "nudge_quiet_hours_end" in payload["tool_policy_required"]
        assert "nudge_quiet_window_active" in payload["tool_policy_required"]
        assert "timers_required" in payload
        assert "reminders_required" in payload
        assert "voice_attention_required" in payload
        assert "turn_choreography" in payload["voice_attention_required"]
        assert "voice_attention_turn_choreography_required" in payload
        assert "turn_glance_yaw" in payload["voice_attention_turn_choreography_required"]
        assert "turn_timeouts_required" in payload
        assert "act_sec" in payload["turn_timeouts_required"]
        assert "integrations_required" in payload
        assert "email" in payload["integrations_required"]
        assert "channels" in payload["integrations_required"]
        assert "identity_required" in payload
        assert "enabled" in payload["identity_required"]
        assert "user_profiles" in payload["identity_required"]
        assert "skills_required" in payload
        assert "observability_required" in payload
        assert "intent_metrics" in payload["observability_required"]
        assert "observability_intent_metrics_required" in payload
        assert "completion_success_rate" in payload["observability_intent_metrics_required"]
        assert "plan_preview_required" in payload
        assert "strict_mode" in payload["plan_preview_required"]
        assert "retention_policy_required" in payload

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

    def test_audit_log_rotation_rolls_existing_backups_at_max_count(self, tmp_path):
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        services._audit_log_max_bytes = 8
        services._audit_log_backups = 2
        services.AUDIT_LOG.write_text("main-old-entry")
        (tmp_path / "audit.jsonl.1").write_text("backup-one")
        (tmp_path / "audit.jsonl.2").write_text("backup-two")

        services._rotate_audit_log_if_needed()

        assert not services.AUDIT_LOG.exists()
        assert (tmp_path / "audit.jsonl.1").read_text() == "main-old-entry"
        assert (tmp_path / "audit.jsonl.2").read_text() == "backup-one"

    def test_audit_log_rotation_errors_are_logged(self, tmp_path, monkeypatch, caplog):
        from jarvis.tools import services

        services.AUDIT_LOG = tmp_path / "audit.jsonl"
        services._audit_log_max_bytes = 1
        services._audit_log_backups = 1
        services.AUDIT_LOG.write_text("this is large enough to rotate")
        backup = tmp_path / "audit.jsonl.1"
        backup.write_text("existing-backup")

        original_unlink = services.Path.unlink

        def _failing_unlink(path, *args, **kwargs):
            if path == backup:
                raise OSError("unlink failed")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(services.Path, "unlink", _failing_unlink)

        with caplog.at_level(logging.WARNING):
            services._rotate_audit_log_if_needed()

        assert "Failed to rotate audit log" in caplog.text

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

    def test_service_schema_integer_fields_are_declared_integer(self):
        from jarvis.tools import services

        schemas = services.SERVICE_TOOL_SCHEMAS
        assert schemas["todoist_add_task"]["properties"]["priority"]["type"] == "integer"
        assert schemas["todoist_list_tasks"]["properties"]["limit"]["type"] == "integer"
        assert schemas["pushover_notify"]["properties"]["priority"]["type"] == "integer"
        assert schemas["memory_search"]["properties"]["limit"]["type"] == "integer"
        assert schemas["memory_update"]["properties"]["memory_id"]["type"] == "integer"
        assert schemas["memory_forget"]["properties"]["memory_id"]["type"] == "integer"
        assert schemas["memory_recent"]["properties"]["limit"]["type"] == "integer"
        assert schemas["memory_summary_list"]["properties"]["limit"]["type"] == "integer"
        assert schemas["task_plan_update"]["properties"]["plan_id"]["type"] == "integer"
        assert schemas["task_plan_update"]["properties"]["step_index"]["type"] == "integer"
        assert schemas["task_plan_summary"]["properties"]["plan_id"]["type"] == "integer"
        assert schemas["task_plan_next"]["properties"]["plan_id"]["type"] == "integer"
        assert schemas["timer_cancel"]["properties"]["timer_id"]["type"] == "integer"
        assert schemas["reminder_list"]["properties"]["limit"]["type"] == "integer"
        assert schemas["reminder_complete"]["properties"]["reminder_id"]["type"] == "integer"
        assert schemas["reminder_notify_due"]["properties"]["limit"]["type"] == "integer"
        assert schemas["reminder_notify_due"]["properties"]["nudge_policy"]["type"] == "string"
        assert schemas["calendar_events"]["properties"]["limit"]["type"] == "integer"
        assert schemas["email_summary"]["properties"]["limit"]["type"] == "integer"
        assert schemas["webhook_inbound_list"]["properties"]["limit"]["type"] == "integer"
        assert schemas["tool_summary"]["properties"]["limit"]["type"] == "integer"
        assert schemas["tool_summary_text"]["properties"]["limit"]["type"] == "integer"

    def test_service_schema_identity_fields_present_for_mutating_tools(self):
        from jarvis.tools import services

        schemas = services.SERVICE_TOOL_SCHEMAS
        for tool_name in [
            "smart_home",
            "home_assistant_conversation",
            "home_assistant_todo",
            "home_assistant_timer",
            "media_control",
            "webhook_trigger",
            "slack_notify",
            "discord_notify",
            "email_send",
            "todoist_add_task",
        ]:
            props = schemas[tool_name]["properties"]
            assert "requester_id" in props
            assert "request_context" in props
            assert "speaker_verified" in props
            assert "approved" in props
            assert "approval_code" in props

    def test_bind_clears_action_history(self, config):
        from jarvis.tools import services

        services._action_last_seen.clear()
        services._action_last_seen["light:turn_on:light.kitchen"] = 123.0
        assert services._action_last_seen

        services.bind(config)

        assert services._action_last_seen == {}

    def test_fault_subset_selector_covers_critical_taxonomy_codes(self):
        project_root = Path(__file__).resolve().parents[1]
        script_text = (project_root / "scripts" / "test_faults.sh").read_text()
        makefile_text = (project_root / "Makefile").read_text()

        # Keep Makefile and script contract coupled through delegation.
        assert "./scripts/test_faults.sh" in makefile_text

        critical_codes = {
            "timeout",
            "cancelled",
            "invalid_json",
            "api_error",
            "storage_error",
            "missing_store",
            "unknown_error",
            "summary_unavailable",
            "http_error",
            "network_client_error",
        }
        for code in critical_codes:
            assert code in script_text

    def test_error_taxonomy_doc_mentions_home_assistant_conversation_timers_reminders_calendar(self):
        project_root = Path(__file__).resolve().parents[1]
        taxonomy_doc = (project_root / "docs" / "operations" / "error-taxonomy.md").read_text()
        assert "home_assistant_conversation" in taxonomy_doc
        assert "timer_cancel" in taxonomy_doc
        assert "timer_*" in taxonomy_doc
        assert "reminder_" in taxonomy_doc
        assert "calendar_" in taxonomy_doc
        assert "home_assistant_todo" in taxonomy_doc
        assert "home_assistant_timer" in taxonomy_doc
        assert "home_assistant_area_entities" in taxonomy_doc
        assert "media_control" in taxonomy_doc
        assert "weather_lookup" in taxonomy_doc
        assert "webhook_trigger" in taxonomy_doc
        assert "slack_notify" in taxonomy_doc
        assert "discord_notify" in taxonomy_doc
        assert "email_send" in taxonomy_doc

    @pytest.mark.asyncio
    async def test_skills_lifecycle_tools(self, tmp_path):
        from jarvis.skills import SkillRegistry
        from jarvis.tools import services

        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "weather_plus"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.json").write_text(
            json.dumps(
                {
                    "name": "weather_plus",
                    "version": "1.0.1",
                    "namespace": "skill.weather_plus",
                    "capabilities": ["forecast"],
                }
            )
        )

        registry = SkillRegistry(skills_dir=str(skills_dir), enabled=True)
        registry.discover()
        services.set_skill_registry(registry)

        listed = await services.skills_list({})
        listed_payload = json.loads(listed["content"][0]["text"])
        assert listed_payload["loaded_count"] == 1
        assert listed_payload["skills"][0]["name"] == "weather_plus"

        disabled = await services.skills_disable({"name": "weather_plus"})
        assert "disabled" in disabled["content"][0]["text"].lower()

        enabled = await services.skills_enable({"name": "weather_plus"})
        assert "enabled" in enabled["content"][0]["text"].lower()

        version = await services.skills_version({"name": "weather_plus"})
        assert json.loads(version["content"][0]["text"]) == {"name": "weather_plus", "version": "1.0.1"}

    @pytest.mark.asyncio
    async def test_skills_list_allowed_when_registry_disabled(self, tmp_path):
        from jarvis.skills import SkillRegistry
        from jarvis.tools import services

        skills_dir = tmp_path / "skills"
        registry = SkillRegistry(skills_dir=str(skills_dir), enabled=False)
        services.set_skill_registry(registry)

        listed = await services.skills_list({})
        payload = json.loads(listed["content"][0]["text"])
        assert payload["enabled"] is False

        denied_enable = await services.skills_enable({"name": "any"})
        assert "tool not permitted" in denied_enable["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_audit_decode_handles_encrypted_without_key(self):
        from jarvis.tools import services

        encrypted_line = json.dumps({"enc": "invalid-token"})
        decoded = services.decode_audit_entry_line(encrypted_line)
        assert decoded is not None
        assert decoded.get("encrypted") is True
        assert decoded.get("error") in {"missing_encryption_key", "invalid_token"}

    def test_prune_audit_file_preserves_encrypted_lines_when_key_missing(self, tmp_path):
        from jarvis.tools import services

        path = tmp_path / "audit.jsonl"
        line = json.dumps({"enc": "not-decryptable"})
        path.write_text(line + "\n")
        removed = services._prune_audit_file(path, cutoff_ts=time.time() + 3600.0)
        assert removed == 0
        assert path.read_text().strip() == line

    @pytest.mark.asyncio
    async def test_inbound_webhook_event_redacts_sensitive_headers(self):
        from jarvis.tools import services

        services._inbound_webhook_events.clear()
        services._inbound_webhook_seq = 1
        event_id = services.record_inbound_webhook_event(
            payload={"ok": True},
            headers={
                "Authorization": "Bearer super-secret",
                "X-Webhook-Token": "token-123",
                "Cookie": "session=abc",
                "X-Custom": "safe",
            },
            source="test",
            path="/hook",
        )
        assert event_id == 1

        listed = await services.webhook_inbound_list({"limit": 1})
        rows = json.loads(listed["content"][0]["text"])
        assert len(rows) == 1
        headers = rows[0]["headers"]
        assert headers["Authorization"] == "***REDACTED***"
        assert headers["X-Webhook-Token"] == "***REDACTED***"
        assert headers["Cookie"] == "***REDACTED***"
        assert headers["X-Custom"] == "safe"

    @pytest.mark.asyncio
    async def test_inbound_webhook_event_sanitizes_payload_size_and_sensitive_keys(self):
        from jarvis.tools import services

        services._inbound_webhook_events.clear()
        services._inbound_webhook_seq = 1
        huge_secret = "x" * 5000
        event_id = services.record_inbound_webhook_event(
            payload={
                "authorization": "Bearer should-hide",
                "nested": {"api_key": "hide-this", "safe": huge_secret},
                "items": list(range(200)),
            },
            headers={"X-Custom": "ok"},
            source="test",
            path="/hook",
        )
        assert event_id == 1

        listed = await services.webhook_inbound_list({"limit": 1})
        rows = json.loads(listed["content"][0]["text"])
        payload = rows[0]["payload"]
        assert payload["authorization"] == "***REDACTED***"
        assert payload["nested"]["api_key"] == "***REDACTED***"
        assert payload["nested"]["safe"].endswith("...<truncated>")
        assert payload["items"][-1].startswith("<truncated_items:")
