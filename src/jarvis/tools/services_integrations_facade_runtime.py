"""Integrations/release helper facade decoupled from services.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.tools.services_integrations_runtime import (
    capture_note as _runtime_capture_note,
    capture_note_notion as _runtime_capture_note_notion,
    evaluate_release_channel as _runtime_evaluate_release_channel,
    load_release_channel_config as _runtime_load_release_channel_config,
    notion_configured as _runtime_notion_configured,
    run_release_channel_check as _runtime_run_release_channel_check,
    write_quality_report_artifact as _runtime_write_quality_report_artifact,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def run_release_channel_check(base: Path, check: dict[str, Any]) -> dict[str, Any]:
    return _runtime_run_release_channel_check(base, check)


def load_release_channel_config() -> tuple[dict[str, Any] | None, str]:
    return _runtime_load_release_channel_config(_services_module())


def evaluate_release_channel(*, channel: str, workspace: Path | None = None) -> dict[str, Any]:
    return _runtime_evaluate_release_channel(
        _services_module(),
        channel=channel,
        workspace=workspace,
    )


def write_quality_report_artifact(payload: dict[str, Any], *, report_path: str | None = None) -> str:
    return _runtime_write_quality_report_artifact(
        _services_module(),
        payload,
        report_path=report_path,
    )


def capture_note(*, backend: str, title: str, content: str, path_hint: str = "") -> dict[str, Any]:
    return _runtime_capture_note(
        _services_module(),
        backend=backend,
        title=title,
        content=content,
        path_hint=path_hint,
    )


def notion_configured() -> bool:
    return _runtime_notion_configured(_services_module())


async def capture_note_notion(*, title: str, content: str) -> tuple[dict[str, Any] | None, str | None]:
    return await _runtime_capture_note_notion(
        _services_module(),
        title=title,
        content=content,
    )
