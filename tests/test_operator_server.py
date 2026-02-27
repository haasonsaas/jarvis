from __future__ import annotations

import json

import aiohttp
import pytest

from jarvis.operator_server import OperatorServer


@pytest.mark.asyncio
async def test_operator_server_routes_and_control_log(tmp_path):
    calls: list[tuple[str, dict]] = []

    async def status_provider():
        return {"status": "ok"}

    async def control_handler(action: str, payload: dict):
        calls.append((action, payload))
        return {"ok": True, "action": action}

    server = OperatorServer(
        host="127.0.0.1",
        port=0,
        status_provider=status_provider,
        diagnostics_provider=lambda: ["warn-1"],
        control_handler=control_handler,
        control_schema_provider=lambda: {"actions": {"set_mode": {"required": ["mode"]}}},
        metrics_provider=lambda: "jarvis_uptime_seconds 1\n",
        events_provider=lambda: [{"event_type": "x", "payload": {"a": 1}}],
        conversation_trace_provider=lambda limit=20: [{"turn_id": 1, "intent": "action"}][:limit],
        inbound_callback=lambda payload, headers, path, source: 7,
        inbound_enabled=False,
        inbound_token="",
        operator_auth_token="",
    )
    await server.start()

    try:
        assert server._site is not None
        sockets = getattr(server._site, "_server").sockets
        port = int(sockets[0].getsockname()[1])
        base = f"http://127.0.0.1:{port}"

        async with aiohttp.ClientSession() as session:
            dashboard = await (await session.get(f"{base}/")).text()
            assert "@media (max-width: 920px)" in dashboard
            assert "Control Schema" in dashboard
            assert "Conversation Trace" in dashboard
            assert "STT Confidence" in dashboard
            assert "Commit Preview" in dashboard
            assert "Operator Brief Profile" in dashboard
            assert "Preset Quiet Hours" in dashboard
            assert "Export Runtime Profile" in dashboard

            bad_control = await session.post(
                f"{base}/api/control",
                data="{not-json",
                headers={"content-type": "application/json"},
            )
            assert bad_control.status == 400
            assert (await bad_control.json())["error"] == "invalid_json"

            status = await (await session.get(f"{base}/api/status")).json()
            assert status["status"] == "ok"

            metrics_text = await (await session.get(f"{base}/metrics")).text()
            assert "jarvis_uptime_seconds" in metrics_text

            events_text = await (await session.get(f"{base}/events?timeout_sec=0.6")).text()
            assert "event: runtime" in events_text

            trace = await (await session.get(f"{base}/api/conversation-trace?limit=5")).json()
            assert trace[0]["turn_id"] == 1

            control_schema = await (await session.get(f"{base}/api/control-schema")).json()
            assert "set_mode" in control_schema["actions"]

            control = await (
                await session.post(
                    f"{base}/api/control",
                    json={
                        "action": "set_mode",
                        "payload": {"mode": "wake_word", "token": "secret-token"},
                    },
                )
            ).json()
            assert control["ok"] is True

            second = await (
                await session.post(
                    f"{base}/api/control",
                    json={"action": "set_mode", "payload": {"mode": "always_listening"}},
                )
            ).json()
            assert second["ok"] is True

            actions = await (await session.get(f"{base}/api/operator-actions")).json()
            assert len(actions) == 2
            newest, oldest = actions[0], actions[1]
            assert oldest["action"] == "set_mode"
            assert oldest["payload"]["token"] == "***REDACTED***"
            assert "signature" in oldest
            assert oldest["signature_alg"] == "hmac-sha256"
            assert newest["previous_signature"] == oldest["signature"]
            assert calls == [
                ("set_mode", {"mode": "wake_word", "token": "secret-token"}),
                ("set_mode", {"mode": "always_listening"}),
            ]
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_operator_server_inbound_webhook_token_enforcement():
    captured: list[dict] = []

    def callback(payload, headers, path, source):
        captured.append(
            {
                "payload": payload,
                "headers": headers,
                "path": path,
                "source": source,
            }
        )
        return 42

    server = OperatorServer(
        host="127.0.0.1",
        port=0,
        status_provider=lambda: _awaitable({"ok": True}),
        diagnostics_provider=lambda: [],
        control_handler=lambda a, p: _awaitable({"ok": True}),
        control_schema_provider=lambda: {"actions": {}},
        metrics_provider=lambda: "",
        events_provider=lambda: [],
        inbound_callback=callback,
        inbound_enabled=True,
        inbound_token="secret-token",
        operator_auth_token="",
    )
    await server.start()

    try:
        assert server._site is not None
        sockets = getattr(server._site, "_server").sockets
        port = int(sockets[0].getsockname()[1])
        base = f"http://127.0.0.1:{port}"

        async with aiohttp.ClientSession() as session:
            forbidden = await session.post(f"{base}/api/webhook/inbound", json={"x": 1})
            assert forbidden.status == 403

            ok_bearer = await session.post(
                f"{base}/api/webhook/inbound",
                headers={"Authorization": "Bearer secret-token"},
                json={"event": "bearer"},
            )
            assert ok_bearer.status == 200

            ok_resp = await session.post(
                f"{base}/api/webhook/inbound",
                headers={"X-Webhook-Token": "secret-token"},
                json={"event": "done"},
            )
            assert ok_resp.status == 200
            payload = await ok_resp.json()
            assert payload == {"ok": True, "event_id": 42}

        assert len(captured) == 2
        assert captured[0]["payload"] == {"event": "bearer"}
        assert captured[0]["path"] == "/api/webhook/inbound"
        assert captured[1]["payload"] == {"event": "done"}
        assert captured[1]["path"] == "/api/webhook/inbound"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_operator_server_inbound_requires_configured_token():
    server = OperatorServer(
        host="127.0.0.1",
        port=0,
        status_provider=lambda: _awaitable({"ok": True}),
        diagnostics_provider=lambda: [],
        control_handler=lambda a, p: _awaitable({"ok": True}),
        control_schema_provider=lambda: {"actions": {}},
        metrics_provider=lambda: "",
        events_provider=lambda: [],
        inbound_callback=lambda payload, headers, path, source: 1,
        inbound_enabled=True,
        inbound_token="",
        operator_auth_token="",
    )
    await server.start()

    try:
        assert server._site is not None
        sockets = getattr(server._site, "_server").sockets
        port = int(sockets[0].getsockname()[1])
        base = f"http://127.0.0.1:{port}"
        async with aiohttp.ClientSession() as session:
            resp = await session.post(f"{base}/api/webhook/inbound", json={"x": 1})
            assert resp.status == 503
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_operator_server_auth_protects_api_endpoints():
    server = OperatorServer(
        host="127.0.0.1",
        port=0,
        status_provider=lambda: _awaitable({"ok": True}),
        diagnostics_provider=lambda: [],
        control_handler=lambda a, p: _awaitable({"ok": True}),
        control_schema_provider=lambda: {"actions": {}},
        metrics_provider=lambda: "jarvis_uptime_seconds 1\n",
        events_provider=lambda: [],
        inbound_callback=lambda payload, headers, path, source: 1,
        inbound_enabled=False,
        inbound_token="",
        operator_auth_token="op-secret",
    )
    await server.start()

    try:
        assert server._site is not None
        sockets = getattr(server._site, "_server").sockets
        port = int(sockets[0].getsockname()[1])
        base = f"http://127.0.0.1:{port}"

        async with aiohttp.ClientSession() as session:
            dashboard = await session.get(f"{base}/")
            assert dashboard.status == 200

            unauth = await session.get(f"{base}/api/status")
            assert unauth.status == 401

            schema_unauth = await session.get(f"{base}/api/control-schema")
            assert schema_unauth.status == 401

            trace_unauth = await session.get(f"{base}/api/conversation-trace")
            assert trace_unauth.status == 401

            denied = await session.get(f"{base}/api/status", headers={"X-Operator-Token": "wrong"})
            assert denied.status == 403

            allowed = await session.get(f"{base}/api/status", headers={"X-Operator-Token": "op-secret"})
            assert allowed.status == 200
            payload = await allowed.json()
            assert payload["ok"] is True

            schema_allowed = await session.get(f"{base}/api/control-schema", headers={"X-Operator-Token": "op-secret"})
            assert schema_allowed.status == 200

            trace_allowed = await session.get(f"{base}/api/conversation-trace", headers={"X-Operator-Token": "op-secret"})
            assert trace_allowed.status == 200

            allowed_bearer = await session.get(
                f"{base}/api/status",
                headers={"Authorization": "Bearer op-secret"},
            )
            assert allowed_bearer.status == 200
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_operator_server_control_maps_invalid_action_to_400():
    async def control_handler(action: str, payload: dict):
        return {"ok": False, "error": "invalid_action", "message": "unknown action"}

    server = OperatorServer(
        host="127.0.0.1",
        port=0,
        status_provider=lambda: _awaitable({"ok": True}),
        diagnostics_provider=lambda: [],
        control_handler=control_handler,
        control_schema_provider=lambda: {"actions": {"set_mode": {"required": ["mode"]}}},
        metrics_provider=lambda: "",
        events_provider=lambda: [],
        inbound_callback=lambda payload, headers, path, source: 1,
        inbound_enabled=False,
        inbound_token="",
        operator_auth_token="",
    )
    await server.start()

    try:
        assert server._site is not None
        sockets = getattr(server._site, "_server").sockets
        port = int(sockets[0].getsockname()[1])
        base = f"http://127.0.0.1:{port}"
        async with aiohttp.ClientSession() as session:
            resp = await session.post(f"{base}/api/control", json={"action": "nope", "payload": {}})
            assert resp.status == 400
            payload = await resp.json()
            assert payload["error"] == "invalid_action"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_operator_server_audit_uses_tail_semantics(monkeypatch, tmp_path):
    log_path = tmp_path / "audit.jsonl"
    rows = [
        {"timestamp": idx, "tool": "x", "args": {"n": idx}}
        for idx in range(1, 241)
    ]
    log_path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr("jarvis.operator_server.AUDIT_LOG", log_path)

    server = OperatorServer(
        host="127.0.0.1",
        port=0,
        status_provider=lambda: _awaitable({"ok": True}),
        diagnostics_provider=lambda: [],
        control_handler=lambda a, p: _awaitable({"ok": True}),
        control_schema_provider=lambda: {"actions": {"set_mode": {"required": ["mode"]}}},
        metrics_provider=lambda: "",
        events_provider=lambda: [],
        inbound_callback=lambda payload, headers, path, source: 1,
        inbound_enabled=False,
        inbound_token="",
        operator_auth_token="",
    )
    await server.start()

    try:
        assert server._site is not None
        sockets = getattr(server._site, "_server").sockets
        port = int(sockets[0].getsockname()[1])
        base = f"http://127.0.0.1:{port}"
        async with aiohttp.ClientSession() as session:
            resp = await session.get(f"{base}/api/audit?limit=5")
            assert resp.status == 200
            payload = await resp.json()
            assert len(payload) == 5
            timestamps = [int(item["timestamp"]) for item in payload]
            assert timestamps == [240, 239, 238, 237, 236]
    finally:
        await server.stop()


async def _awaitable(value):
    return value
