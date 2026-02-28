"""Memory mutation handlers for trust domain."""

from __future__ import annotations

import json
import re
from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional runtime dependency
    OpenAI = None  # type: ignore[assignment]


_CONFLICT_ACTIONS = {"store", "skip_duplicate", "supersede"}


def _services():
    from jarvis.tools import services as s

    return s


def _normalize_conflict_resolution_payload(payload: Any, *, candidate_ids: set[int]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action", "store")).strip().lower()
    if action not in _CONFLICT_ACTIONS:
        action = "store"
    target_memory_id: int | None = None
    raw_target = payload.get("target_memory_id")
    if isinstance(raw_target, bool):
        raw_target = None
    if isinstance(raw_target, int):
        target_memory_id = int(raw_target)
    elif isinstance(raw_target, str):
        text = raw_target.strip()
        if text and (text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit())):
            try:
                target_memory_id = int(text)
            except ValueError:
                target_memory_id = None
    if target_memory_id not in candidate_ids:
        target_memory_id = None
    rewritten_text = str(payload.get("rewritten_text", "")).strip()
    if len(rewritten_text) > 400:
        rewritten_text = rewritten_text[:400].rstrip()
    reason = str(payload.get("reason", "")).strip()
    if len(reason) > 220:
        reason = reason[:220].rstrip()
    return {
        "action": action,
        "target_memory_id": target_memory_id,
        "rewritten_text": rewritten_text,
        "reason": reason,
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _resolve_conflict_decision_sync(
    *,
    incoming_text: str,
    kind: str,
    source: str,
    scope: str,
    candidate_report: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    timeout_sec: float,
) -> dict[str, Any] | None:
    if OpenAI is None:
        return None
    if not str(api_key).strip():
        return None
    clean_model = str(model or "").strip()
    if not clean_model:
        return None
    top_matches = [row for row in candidate_report.get("top_matches", []) if isinstance(row, dict)]
    near_duplicates = [row for row in candidate_report.get("near_duplicates", []) if isinstance(row, dict)]
    contradictions = [row for row in candidate_report.get("contradictions", []) if isinstance(row, dict)]
    if not top_matches and not near_duplicates and not contradictions:
        return None
    candidate_ids = {
        int(row["memory_id"])
        for row in [*top_matches, *near_duplicates, *contradictions]
        if isinstance(row.get("memory_id"), int)
    }
    if not candidate_ids:
        return None
    timeout = max(0.5, float(timeout_sec))
    client_kwargs: dict[str, Any] = {
        "api_key": str(api_key).strip(),
        "timeout": timeout,
    }
    if str(base_url or "").strip():
        client_kwargs["base_url"] = str(base_url).strip()
    client = OpenAI(**client_kwargs)
    system_prompt = (
        "You are resolving memory conflicts for a personal assistant. "
        "Given an incoming memory and candidate existing memories, return JSON only with keys: "
        "action, target_memory_id, rewritten_text, reason. "
        "action must be one of: store, skip_duplicate, supersede. "
        "Use skip_duplicate when incoming memory is materially the same as an existing one. "
        "Use supersede when incoming memory should replace/merge into one existing memory; "
        "provide target_memory_id and rewritten_text. "
        "Use store when incoming memory should be stored as a new memory."
    )
    payload = {
        "incoming": {
            "text": str(incoming_text),
            "kind": str(kind),
            "source": str(source),
            "scope": str(scope),
        },
        "candidates": {
            "top_matches": top_matches[:6],
            "near_duplicates": near_duplicates[:6],
            "contradictions": contradictions[:6],
        },
    }
    response = client.chat.completions.create(
        model=clean_model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ],
    )
    choice = response.choices[0] if response.choices else None
    content = ""
    if choice is not None and getattr(choice, "message", None) is not None:
        content = str(getattr(choice.message, "content", "") or "")
    parsed = _extract_json_object(content)
    return _normalize_conflict_resolution_payload(parsed, candidate_ids=candidate_ids)


async def _resolve_conflict_decision(
    *,
    asyncio_module: Any,
    incoming_text: str,
    kind: str,
    source: str,
    scope: str,
    candidate_report: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    timeout_sec: float,
) -> dict[str, Any] | None:
    if not candidate_report:
        return None
    return await asyncio_module.to_thread(
        _resolve_conflict_decision_sync,
        incoming_text=incoming_text,
        kind=kind,
        source=source,
        scope=scope,
        candidate_report=candidate_report,
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_sec=timeout_sec,
    )

async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _config = s._config
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    _memory_pii_guardrails_enabled = s._memory_pii_guardrails_enabled
    _contains_pii = s._contains_pii
    _as_float = s._as_float
    _normalize_memory_scope = s._normalize_memory_scope
    MEMORY_SCOPES = s.MEMORY_SCOPES
    _memory_scope_for_add = s._memory_scope_for_add
    _memory_scope_tags = s._memory_scope_tags

    start_time = time.monotonic()
    if not _tool_permitted("memory_add"):
        record_summary("memory_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_add", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    allow_pii = _as_bool(args.get("allow_pii"), default=False)
    if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
        _record_service_error("memory_add", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Potential PII detected in memory text. Use allow_pii=true only when intentional.",
                }
            ]
        }
    tags_raw = args.get("tags")
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    kind = str(args.get("kind", "note"))
    importance = _as_float(args.get("importance", 0.5), 0.5, minimum=0.0, maximum=1.0)
    sensitivity = _as_float(args.get("sensitivity", 0.0), 0.0, minimum=0.0, maximum=1.0)
    source = str(args.get("source", "user"))
    requested_scope = args.get("scope")
    if requested_scope is not None and _normalize_memory_scope(requested_scope) is None:
        _record_service_error("memory_add", start_time, "invalid_data")
        scopes_text = ", ".join(sorted(MEMORY_SCOPES))
        return {"content": [{"type": "text", "text": f"scope must be one of: {scopes_text}."}]}
    scope = _memory_scope_for_add(kind=kind, source=source, tags=tags, requested_scope=requested_scope)
    tags = _memory_scope_tags(tags, scope)
    candidate_report: dict[str, Any] | None = None
    if _as_bool(args.get("inspect_candidate"), default=True):
        try:
            candidate_report = _memory.inspect_memory_candidate(
                text,
                limit=3,
                fanout=40,
            )
        except Exception:
            candidate_report = None
    resolve_conflicts = _as_bool(
        args.get("resolve_conflicts"),
        default=_as_bool(getattr(_config, "memory_conflict_resolution_enabled", False), default=False),
    )
    conflict_decision: dict[str, Any] | None = None
    has_conflict_candidates = bool(
        candidate_report
        and (
            candidate_report.get("near_duplicates")
            or candidate_report.get("contradictions")
        )
    )
    if resolve_conflicts and has_conflict_candidates:
        decision_model = str(
            args.get("conflict_resolution_model")
            or getattr(_config, "memory_conflict_resolution_model", "gpt-4.1-mini")
        ).strip()
        decision_base_url = str(getattr(_config, "memory_conflict_resolution_base_url", "")).strip()
        decision_timeout = _as_float(
            getattr(_config, "memory_conflict_resolution_timeout_sec", 4.0),
            4.0,
            minimum=0.5,
            maximum=30.0,
        )
        try:
            conflict_decision = await _resolve_conflict_decision(
                asyncio_module=asyncio,
                incoming_text=text,
                kind=kind,
                source=source,
                scope=scope,
                candidate_report=candidate_report or {},
                api_key=str(getattr(_config, "openai_api_key", "")).strip(),
                model=decision_model,
                base_url=decision_base_url,
                timeout_sec=decision_timeout,
            )
        except Exception:
            conflict_decision = None
    if conflict_decision:
        decision_action = str(conflict_decision.get("action", "store"))
        decision_target = conflict_decision.get("target_memory_id")
        decision_reason = str(conflict_decision.get("reason", "")).strip()
        decision_rewrite = str(conflict_decision.get("rewritten_text", "")).strip()
        if decision_action == "skip_duplicate" and isinstance(decision_target, int):
            reason_suffix = f" Reason: {decision_reason}" if decision_reason else ""
            record_summary(
                "memory_add",
                "ok",
                start_time,
                effect=f"duplicate_skip={decision_target}",
                risk="low",
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Memory skipped as duplicate of id={decision_target}.{reason_suffix}",
                    }
                ]
            }
        if decision_action == "supersede" and isinstance(decision_target, int):
            merged_text = decision_rewrite or text
            try:
                merged = _memory.update_memory_text(decision_target, merged_text)
            except Exception:
                merged = False
            if merged:
                reason_suffix = f" Reason: {decision_reason}" if decision_reason else ""
                record_summary(
                    "memory_add",
                    "ok",
                    start_time,
                    effect=f"memory_supersede={decision_target}",
                    risk="low",
                )
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Memory merged into existing entry (id={decision_target}, scope={scope}).{reason_suffix}",
                        }
                    ]
                }
        if decision_rewrite:
            text = decision_rewrite
            if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
                _record_service_error("memory_add", start_time, "policy")
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Potential PII detected in rewritten memory text. Use allow_pii=true only when intentional.",
                        }
                    ]
                }
    try:
        memory_id = _memory.add_memory(
            text,
            kind=kind,
            tags=tags,
            importance=importance,
            sensitivity=sensitivity,
            source=source,
        )
    except Exception as e:
        _record_service_error("memory_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory add failed: {e}"}]}
    record_summary("memory_add", "ok", start_time)
    message = f"Memory stored (id={memory_id}, scope={scope})."
    if candidate_report:
        duplicate_ids = [
            int(row["memory_id"])
            for row in candidate_report.get("near_duplicates", [])
            if isinstance(row, dict) and isinstance(row.get("memory_id"), int)
        ]
        contradiction_rows = [
            row
            for row in candidate_report.get("contradictions", [])
            if isinstance(row, dict) and isinstance(row.get("memory_id"), int)
        ]
        if duplicate_ids:
            duplicate_text = ",".join(str(memory_key) for memory_key in duplicate_ids[:3])
            message += f" Potential duplicate candidate(s): {duplicate_text}."
        if contradiction_rows:
            contradiction_ids = ",".join(str(int(row["memory_id"])) for row in contradiction_rows[:3])
            subjects = sorted(
                {
                    str(row.get("subject", "")).strip()
                    for row in contradiction_rows
                    if str(row.get("subject", "")).strip()
                }
            )
            subject_text = ",".join(subjects[:3]) if subjects else "assertion"
            message += f" Potential contradiction candidate(s): {contradiction_ids} on {subject_text}."
    return {"content": [{"type": "text", "text": message}]}


async def memory_update(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int
    _as_bool = s._as_bool
    _memory_pii_guardrails_enabled = s._memory_pii_guardrails_enabled
    _contains_pii = s._contains_pii

    start_time = time.monotonic()
    if not _tool_permitted("memory_update"):
        record_summary("memory_update", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_update", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    memory_id = _as_exact_int(args.get("memory_id"))
    if memory_id is None or memory_id <= 0:
        _record_service_error("memory_update", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "memory_id must be a positive integer."}]}
    text = str(args.get("text", "")).strip()
    if not text:
        _record_service_error("memory_update", start_time, "missing_text")
        return {"content": [{"type": "text", "text": "Memory text required."}]}
    allow_pii = _as_bool(args.get("allow_pii"), default=False)
    if _memory_pii_guardrails_enabled and not allow_pii and _contains_pii(text):
        _record_service_error("memory_update", start_time, "policy")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Potential PII detected in memory text. Use allow_pii=true only when intentional.",
                }
            ]
        }
    try:
        updated = _memory.update_memory_text(memory_id, text)
    except Exception as e:
        _record_service_error("memory_update", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory update failed: {e}"}]}
    if not updated:
        _record_service_error("memory_update", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Memory not found."}]}
    record_summary("memory_update", "ok", start_time, effect=f"memory_id={memory_id}", risk="low")
    return {"content": [{"type": "text", "text": f"Memory updated (id={memory_id})."}]}


async def memory_forget(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_exact_int = s._as_exact_int

    start_time = time.monotonic()
    if not _tool_permitted("memory_forget"):
        record_summary("memory_forget", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_forget", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    memory_id = _as_exact_int(args.get("memory_id"))
    if memory_id is None or memory_id <= 0:
        _record_service_error("memory_forget", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "memory_id must be a positive integer."}]}
    try:
        deleted = _memory.delete_memory(memory_id)
    except Exception as e:
        _record_service_error("memory_forget", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory forget failed: {e}"}]}
    if not deleted:
        _record_service_error("memory_forget", start_time, "not_found")
        return {"content": [{"type": "text", "text": "Memory not found."}]}
    record_summary("memory_forget", "ok", start_time, effect=f"memory_id={memory_id}", risk="low")
    return {"content": [{"type": "text", "text": f"Memory forgotten (id={memory_id})."}]}
