from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis.runtime_operator_server import (
    operator_events_provider,
    operator_metrics_provider,
    start_operator_server,
    startup_diagnostics_provider,
    stop_operator_server,
)


class _FakeObservability:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def prometheus_metrics(self) -> str:
        return "metric_a 1\n"

    def recent_events(self, *, limit: int = 100) -> list[dict[str, object]]:
        return [{"name": "event", "limit": limit}]

    def record_event(self, name: str, payload: dict[str, object]) -> None:
        self.events.append((name, payload))


class _FakeServer:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _runtime_stub() -> SimpleNamespace:
    cfg = SimpleNamespace(
        startup_warnings=["warn-a"],
        operator_server_enabled=True,
        operator_server_host="127.0.0.1",
        operator_server_port=8777,
        webhook_inbound_enabled=True,
        webhook_inbound_token="inbound-token",
        webhook_auth_token="auth-token",
        operator_auth_mode="token",
        operator_auth_token="operator-token",
    )
    runtime = SimpleNamespace(
        config=cfg,
        _operator_server=None,
        _observability=_FakeObservability(),
        _startup_blockers=lambda: ["block-a"],
        _startup_diagnostics_provider=lambda: ["warn-a", "BLOCKER: block-a"],
        _operator_status_provider=lambda: None,
        _operator_control_handler=lambda action, payload: None,
        _operator_control_schema=lambda: {},
        _operator_metrics_provider=lambda: "",
        _operator_events_provider=lambda: [],
        _operator_conversation_trace_provider=lambda limit=20: [],
    )
    return runtime


def test_startup_diagnostics_provider_merges_warnings_and_blockers() -> None:
    runtime = _runtime_stub()
    items = startup_diagnostics_provider(runtime)
    assert items == ["warn-a", "BLOCKER: block-a"]


def test_operator_metrics_and_events_provider_use_observability() -> None:
    runtime = _runtime_stub()
    assert operator_metrics_provider(runtime) == "metric_a 1\n"
    assert operator_events_provider(runtime) == [{"name": "event", "limit": 100}]


@pytest.mark.asyncio
async def test_start_operator_server_sets_handle_and_wires_inbound_callback() -> None:
    runtime = _runtime_stub()
    recorded: list[dict[str, object]] = []
    logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)

    def _record_inbound(**kwargs) -> int:
        recorded.append({str(k): v for k, v in kwargs.items()})
        return 42

    await start_operator_server(
        runtime,
        operator_server_class=_FakeServer,
        record_inbound_webhook_event_fn=_record_inbound,
        logger=logger,
    )

    assert isinstance(runtime._operator_server, _FakeServer)
    assert runtime._operator_server.started is True
    callback = runtime._operator_server.kwargs["inbound_callback"]
    result = callback({"x": 1}, {"h": "v"}, "/inbound", "test")
    assert result == 42
    assert recorded == [
        {"payload": {"x": 1}, "headers": {"h": "v"}, "path": "/inbound", "source": "test"}
    ]
    assert runtime._observability.events
    assert runtime._observability.events[0][0] == "operator_server_started"


@pytest.mark.asyncio
async def test_stop_operator_server_clears_handle() -> None:
    runtime = _runtime_stub()
    runtime._operator_server = _FakeServer()
    await stop_operator_server(runtime)
    assert runtime._operator_server is None
