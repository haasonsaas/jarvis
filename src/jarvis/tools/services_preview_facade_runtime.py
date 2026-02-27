"""Plan-preview helper facade decoupled from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_preview_runtime import (
    consume_plan_preview_token as _runtime_consume_plan_preview_token,
    is_ambiguous_entity_target as _runtime_is_ambiguous_entity_target,
    is_ambiguous_high_risk_text as _runtime_is_ambiguous_high_risk_text,
    issue_plan_preview_token as _runtime_issue_plan_preview_token,
    plan_preview_message as _runtime_plan_preview_message,
    plan_preview_signature as _runtime_plan_preview_signature,
    preview_gate as _runtime_preview_gate,
    prune_plan_previews as _runtime_prune_plan_previews,
    tokenized_words as _runtime_tokenized_words,
)


def _services_module() -> Any:
    from jarvis.tools import services

    return services


def tokenized_words(text: str) -> list[str]:
    return _runtime_tokenized_words(text)


def is_ambiguous_high_risk_text(text: str) -> bool:
    return _runtime_is_ambiguous_high_risk_text(_services_module(), text)


def is_ambiguous_entity_target(entity_id: str) -> bool:
    return _runtime_is_ambiguous_entity_target(entity_id)


def plan_preview_signature(tool_name: str, payload: dict[str, Any]) -> str:
    return _runtime_plan_preview_signature(tool_name, payload)


def prune_plan_previews(now_ts: float | None = None) -> None:
    _runtime_prune_plan_previews(_services_module(), now_ts=now_ts)


def issue_plan_preview_token(tool_name: str, signature: str, risk: str, summary: str) -> str:
    return _runtime_issue_plan_preview_token(_services_module(), tool_name, signature, risk, summary)


def consume_plan_preview_token(token: str, *, tool_name: str, signature: str) -> bool:
    return _runtime_consume_plan_preview_token(_services_module(), token, tool_name=tool_name, signature=signature)


def plan_preview_message(*, summary: str, risk: str, token: str, ttl_sec: float) -> str:
    return _runtime_plan_preview_message(summary=summary, risk=risk, token=token, ttl_sec=ttl_sec)


def preview_gate(
    *,
    tool_name: str,
    args: dict[str, Any],
    risk: str,
    summary: str,
    signature_payload: dict[str, Any],
    enforce_default: bool,
) -> str | None:
    return _runtime_preview_gate(
        _services_module(),
        tool_name=tool_name,
        args=args,
        risk=risk,
        summary=summary,
        signature_payload=signature_payload,
        enforce_default=enforce_default,
    )
