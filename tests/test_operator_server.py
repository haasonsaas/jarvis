from __future__ import annotations

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
        metrics_provider=lambda: "jarvis_uptime_seconds 1\n",
        events_provider=lambda: [{"event_type": "x", "payload": {"a": 1}}],
        inbound_callback=lambda payload, headers, path, source: 7,
        inbound_enabled=False,
        inbound_token="",
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

            control = await (
                await session.post(
                    f"{base}/api/control",
                    json={"action": "set_mode", "payload": {"mode": "wake_word"}},
                )
            ).json()
            assert control["ok"] is True

            actions = await (await session.get(f"{base}/api/operator-actions")).json()
            assert len(actions) == 1
            assert actions[0]["action"] == "set_mode"
            assert calls == [("set_mode", {"mode": "wake_word"})]
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
        metrics_provider=lambda: "",
        events_provider=lambda: [],
        inbound_callback=callback,
        inbound_enabled=True,
        inbound_token="secret-token",
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

            ok_resp = await session.post(
                f"{base}/api/webhook/inbound",
                headers={"X-Webhook-Token": "secret-token"},
                json={"event": "done"},
            )
            assert ok_resp.status == 200
            payload = await ok_resp.json()
            assert payload == {"ok": True, "event_id": 42}

        assert len(captured) == 1
        assert captured[0]["payload"] == {"event": "done"}
        assert captured[0]["path"] == "/api/webhook/inbound"
    finally:
        await server.stop()


async def _awaitable(value):
    return value
