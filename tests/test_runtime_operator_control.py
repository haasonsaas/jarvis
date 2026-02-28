from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from jarvis.runtime_operator_control import handle_operator_control


def _runtime_stub() -> SimpleNamespace:
    return SimpleNamespace(
        _voice_controller=lambda: SimpleNamespace(),
        _operator_available_actions=lambda: [],
        _parse_control_bool=lambda value: value if isinstance(value, bool) else None,
    )


def _tool_payload(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


@pytest.mark.asyncio
async def test_operator_control_lists_pending_approvals(monkeypatch) -> None:
    runtime = _runtime_stub()

    async def _fake_home_orchestrator(args: dict) -> dict:
        assert args["action"] == "approval_list"
        return _tool_payload(
            {
                "action": "approval_list",
                "pending_count": 1,
                "status_counts": {"pending": 1},
                "approvals": [{"approval_id": "approval-1", "status": "pending"}],
            }
        )

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.home_orchestrator", _fake_home_orchestrator)

    result = await handle_operator_control(runtime, "list_pending_approvals", {"limit": 5})
    assert result["ok"] is True
    assert result["pending_count"] == 1
    assert result["approvals"][0]["approval_id"] == "approval-1"


@pytest.mark.asyncio
async def test_operator_control_resolve_approval_with_execute(monkeypatch) -> None:
    runtime = _runtime_stub()
    calls: list[dict] = []

    async def _fake_home_orchestrator(args: dict) -> dict:
        calls.append(dict(args))
        if args["action"] == "approval_resolve":
            return _tool_payload(
                {
                    "action": "approval_resolve",
                    "resolved": True,
                    "approved": True,
                    "execution_ticket": "ticket-123",
                }
            )
        if args["action"] == "execute":
            return _tool_payload({"action": "execute", "live_executed_count": 1})
        raise AssertionError(f"unexpected action: {args}")

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.home_orchestrator", _fake_home_orchestrator)

    result = await handle_operator_control(
        runtime,
        "resolve_approval",
        {
            "approval_id": "approval-7",
            "approved": True,
            "execute": True,
        },
    )
    assert result["ok"] is True
    assert result["approval"]["resolved"] is True
    assert result["execution"]["live_executed_count"] == 1
    assert calls[0]["action"] == "approval_resolve"
    assert calls[0]["__operator_identity"] == "operator"
    assert calls[1]["action"] == "execute"
    assert calls[1]["execution_ticket"] == "ticket-123"
    assert calls[1]["resolver_id"] == "operator"
    assert calls[1]["requester_id"] == "operator"
    assert calls[1]["__operator_identity"] == "operator"


@pytest.mark.asyncio
async def test_operator_control_resolve_approval_uses_operator_identity_not_payload(monkeypatch) -> None:
    runtime = _runtime_stub()
    calls: list[dict] = []

    async def _fake_home_orchestrator(args: dict) -> dict:
        calls.append(dict(args))
        if args["action"] == "approval_resolve":
            return _tool_payload({"action": "approval_resolve", "resolved": True, "approved": True})
        raise AssertionError(f"unexpected action: {args}")

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.home_orchestrator", _fake_home_orchestrator)

    result = await handle_operator_control(
        runtime,
        "resolve_approval",
        {
            "approval_id": "approval-7",
            "approved": True,
            "resolver_id": "spoofed-user",
            "__operator_identity": "session-abc123",
        },
    )
    assert result["ok"] is True
    assert calls[0]["resolver_id"] == "session-abc123"
    assert calls[0]["__operator_identity"] == "session-abc123"


@pytest.mark.asyncio
async def test_operator_control_dead_letter_status_and_replay(monkeypatch) -> None:
    runtime = _runtime_stub()

    async def _fake_dead_letter_list(args: dict) -> dict:
        assert args["status"] == "open"
        return _tool_payload({"pending_count": 2, "failed_count": 1})

    async def _fake_dead_letter_replay(args: dict) -> dict:
        assert args["status"] == "open"
        assert args["dry_run"] is True
        return _tool_payload({"attempted_count": 2, "failed_count": 0})

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.dead_letter_list", _fake_dead_letter_list)
    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.dead_letter_replay", _fake_dead_letter_replay)

    status = await handle_operator_control(runtime, "dead_letter_status", {"status_filter": "open"})
    replay = await handle_operator_control(
        runtime,
        "dead_letter_replay",
        {"status_filter": "open", "dry_run": True},
    )
    assert status["ok"] is True
    assert status["dead_letter_queue"]["pending_count"] == 2
    assert replay["ok"] is True
    assert replay["dead_letter_replay"]["attempted_count"] == 2


@pytest.mark.asyncio
async def test_operator_control_resolve_approval_execute_requires_execution_ticket(monkeypatch) -> None:
    runtime = _runtime_stub()

    async def _fake_home_orchestrator(args: dict) -> dict:
        if args["action"] == "approval_resolve":
            return _tool_payload({"action": "approval_resolve", "resolved": True, "approved": True})
        raise AssertionError(f"unexpected action: {args}")

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.home_orchestrator", _fake_home_orchestrator)

    result = await handle_operator_control(
        runtime,
        "resolve_approval",
        {
            "approval_id": "approval-7",
            "approved": True,
            "execute": True,
        },
    )
    assert result["ok"] is False
    assert result["error"] == "execution_ticket_missing"


@pytest.mark.asyncio
async def test_operator_control_lists_autonomy_replans(monkeypatch) -> None:
    runtime = _runtime_stub()

    async def _fake_planner_engine(args: dict) -> dict:
        assert args["action"] == "autonomy_status"
        return _tool_payload(
            {
                "action": "autonomy_status",
                "needs_replan_count": 1,
                "retry_pending_count": 2,
                "failure_taxonomy": {"condition_equals_mismatch": 3},
                "task_progress": [
                    {"id": "deferred-1", "status": "needs_replan", "needs_replan": True},
                    {"id": "deferred-2", "status": "scheduled", "needs_replan": False},
                ],
            }
        )

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.planner_engine", _fake_planner_engine)

    result = await handle_operator_control(runtime, "list_autonomy_replans", {"limit": 10})
    assert result["ok"] is True
    assert result["needs_replan_count"] == 1
    assert result["retry_pending_count"] == 2
    assert result["tasks"] == [{"id": "deferred-1", "status": "needs_replan", "needs_replan": True}]


@pytest.mark.asyncio
async def test_operator_control_apply_autonomy_replan_uses_operator_identity(monkeypatch) -> None:
    runtime = _runtime_stub()
    calls: list[dict] = []

    async def _fake_planner_engine(args: dict) -> dict:
        calls.append(dict(args))
        assert args["action"] == "autonomy_replan"
        return _tool_payload({"action": "autonomy_replan", "task_id": args["task_id"]})

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.planner_engine", _fake_planner_engine)

    result = await handle_operator_control(
        runtime,
        "apply_autonomy_replan",
        {
            "task_id": "deferred-9",
            "plan_steps": ["step-a", "step-b"],
            "step_contracts": [{}, {}],
            "reset_progress": True,
            "resolver_id": "spoofed",
            "__operator_identity": "session-abc123",
            "notes": "operator fix",
        },
    )
    assert result["ok"] is True
    assert result["autonomy_replan"]["task_id"] == "deferred-9"
    assert calls[0]["resolver_id"] == "session-abc123"
    assert calls[0]["task_id"] == "deferred-9"
    assert calls[0]["plan_steps"] == ["step-a", "step-b"]


@pytest.mark.asyncio
async def test_operator_control_copilot_actions(monkeypatch) -> None:
    runtime = _runtime_stub()

    async def _fake_system_status(args: dict) -> dict:
        assert args == {}
        return _tool_payload(
            {
                "expansion": {
                    "proactive": {"approval_pending_count": 1},
                    "planner_engine": {
                        "autonomy_needs_replan_count": 1,
                        "autonomy_slo": {"alert_count": 1},
                    },
                },
                "dead_letter_queue": {"pending_count": 2},
            }
        )

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.system_status", _fake_system_status)

    result = await handle_operator_control(runtime, "copilot_actions", {})
    assert result["ok"] is True
    action_ids = {
        row["action_id"]
        for row in result["actions"]
        if isinstance(row, dict) and isinstance(row.get("action_id"), str)
    }
    assert "pending_approvals" in action_ids
    assert "autonomy_replans" in action_ids
    assert "dead_letter_replay_dry_run" in action_ids
    assert "autonomy_slo_alerts" in action_ids


@pytest.mark.asyncio
async def test_operator_control_copilot_execute_dispatches(monkeypatch) -> None:
    runtime = _runtime_stub()

    async def _fake_system_status(args: dict) -> dict:
        assert args == {}
        return _tool_payload(
            {
                "expansion": {"proactive": {"approval_pending_count": 0}, "planner_engine": {}},
                "dead_letter_queue": {"pending_count": 1},
            }
        )

    async def _fake_dead_letter_replay(args: dict) -> dict:
        assert args["dry_run"] is True
        return _tool_payload({"attempted_count": 1, "failed_count": 0})

    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.system_status", _fake_system_status)
    monkeypatch.setattr("jarvis.runtime_operator_control.service_tools.dead_letter_replay", _fake_dead_letter_replay)

    result = await handle_operator_control(
        runtime,
        "copilot_execute",
        {"action_id": "dead_letter_replay_dry_run"},
    )
    assert result["ok"] is True
    assert result["dead_letter_replay"]["attempted_count"] == 1
