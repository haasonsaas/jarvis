"""Operator server lifecycle and provider runtime helpers."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Callable


def startup_diagnostics_provider(runtime: Any) -> list[str]:
    warnings = list(getattr(runtime.config, "startup_warnings", []))
    blockers = runtime._startup_blockers()
    return [*warnings, *[f"BLOCKER: {item}" for item in blockers]]


def operator_metrics_provider(runtime: Any) -> str:
    observability = getattr(runtime, "_observability", None)
    if observability is None:
        return ""
    with suppress(Exception):
        return observability.prometheus_metrics()
    return ""


def operator_events_provider(runtime: Any) -> list[dict[str, Any]]:
    observability = getattr(runtime, "_observability", None)
    if observability is None:
        return []
    with suppress(Exception):
        return observability.recent_events(limit=100)
    return []


async def start_operator_server(
    runtime: Any,
    *,
    operator_server_class: Any,
    record_inbound_webhook_event_fn: Callable[..., int],
    logger: Any,
) -> None:
    if not runtime.config.operator_server_enabled:
        return
    if runtime._operator_server is not None:
        return
    server = operator_server_class(
        host=runtime.config.operator_server_host,
        port=runtime.config.operator_server_port,
        status_provider=runtime._operator_status_provider,
        diagnostics_provider=runtime._startup_diagnostics_provider,
        control_handler=runtime._operator_control_handler,
        control_schema_provider=runtime._operator_control_schema,
        metrics_provider=runtime._operator_metrics_provider,
        events_provider=runtime._operator_events_provider,
        conversation_trace_provider=runtime._operator_conversation_trace_provider,
        inbound_callback=lambda payload, headers, path, source: record_inbound_webhook_event_fn(
            payload=payload,
            headers=headers,
            path=path,
            source=source,
        ),
        inbound_enabled=runtime.config.webhook_inbound_enabled,
        inbound_token=runtime.config.webhook_inbound_token or runtime.config.webhook_auth_token,
        operator_auth_mode=runtime.config.operator_auth_mode,
        operator_auth_token=runtime.config.operator_auth_token,
    )
    try:
        await server.start()
    except Exception as exc:
        logger.warning("Operator server failed to start: %s", exc)
        return
    runtime._operator_server = server
    observability = getattr(runtime, "_observability", None)
    if observability is not None:
        with suppress(Exception):
            observability.record_event(
                "operator_server_started",
                {
                    "host": runtime.config.operator_server_host,
                    "port": runtime.config.operator_server_port,
                },
            )


async def stop_operator_server(runtime: Any) -> None:
    server = getattr(runtime, "_operator_server", None)
    if server is None:
        return
    with suppress(Exception):
        await server.stop()
    runtime._operator_server = None
