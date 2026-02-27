"""Proactive/trust/memory-governance domain handlers extracted from services.py."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_proactive_runtime import (
    has_recent_dispatch as _has_recent_dispatch,
    nudge_bucket as _nudge_bucket,
    nudge_fingerprint as _nudge_fingerprint,
    nudge_reason_counts as _nudge_reason_counts,
    nudge_row_score as _nudge_row_score,
    nudge_severity as _nudge_severity,
    prune_recent_dispatches as _prune_recent_dispatches,
    record_recent_dispatch as _record_recent_dispatch,
)


def _services():
    from jarvis.tools import services as s

    return s


async def proactive_assistant(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _proactive_state = s._proactive_state
    _expansion_payload_response = s._expansion_payload_response
    _as_int = s._as_int
    _as_bool = s._as_bool
    _normalize_nudge_policy = s._normalize_nudge_policy
    _nudge_policy = s._nudge_policy
    _quiet_window_active = s._quiet_window_active
    NUDGE_RECENT_DISPATCH_MAX = s.NUDGE_RECENT_DISPATCH_MAX

    start_time = time.monotonic()
    if not _tool_permitted("proactive_assistant"):
        record_summary("proactive_assistant", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    action = str(args.get("action", "")).strip().lower()
    now = time.time()
    if action == "briefing":
        mode = str(args.get("mode", "morning")).strip().lower() or "morning"
        calendar = args.get("calendar") if isinstance(args.get("calendar"), list) else []
        reminders = args.get("reminders") if isinstance(args.get("reminders"), list) else []
        weather = args.get("weather") if isinstance(args.get("weather"), dict) else {}
        home_state = args.get("home_state") if isinstance(args.get("home_state"), dict) else {}
        due_reminders = 0
        for row in reminders:
            if not isinstance(row, dict):
                continue
            if str(row.get("status", "pending")).strip().lower() == "completed":
                continue
            due_at = _as_float(row.get("due_at", row.get("due", now + 1_000_000)), now + 1_000_000)
            if due_at <= now:
                due_reminders += 1
        next_event = ""
        for row in calendar:
            if isinstance(row, dict):
                next_event = str(row.get("summary") or row.get("title") or "").strip()
                if next_event:
                    break
        weather_text = str(weather.get("summary") or weather.get("condition") or "No weather update").strip()
        home_alerts = int(home_state.get("alerts", 0) or 0) if isinstance(home_state, dict) else 0
        _proactive_state["last_briefing_at"] = now
        payload = {
            "action": action,
            "mode": mode,
            "next_event": next_event,
            "calendar_items": len(calendar),
            "due_reminders": due_reminders,
            "weather": weather_text,
            "home_alerts": home_alerts,
            "briefing": (
                f"{mode.title()} briefing: {len(calendar)} calendar items, {due_reminders} due reminders, "
                f"weather '{weather_text}', home alerts={home_alerts}."
            ),
        }
        record_summary("proactive_assistant", "ok", start_time, effect=f"briefing:{mode}", risk="low")
        return _expansion_payload_response(payload)

    if action == "anomaly_scan":
        devices = args.get("devices") if isinstance(args.get("devices"), list) else []
        reminders = args.get("reminders") if isinstance(args.get("reminders"), list) else []
        anomalies: list[dict[str, Any]] = []
        for row in devices:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("entity_id") or "device").strip()
            status = str(row.get("status") or row.get("state") or "").strip().lower()
            if status in {"offline", "unavailable", "disconnected"}:
                anomalies.append({"type": "device_offline", "entity": name, "severity": "high"})
            temp = row.get("temperature")
            expected_min = row.get("expected_min")
            expected_max = row.get("expected_max")
            if temp is not None and expected_min is not None and expected_max is not None:
                current_temp = _as_float(temp, 0.0)
                low = _as_float(expected_min, 0.0)
                high = _as_float(expected_max, 100.0)
                if current_temp < low or current_temp > high:
                    anomalies.append(
                        {
                            "type": "temperature_outlier",
                            "entity": name,
                            "severity": "medium",
                            "temperature": current_temp,
                            "expected_min": low,
                            "expected_max": high,
                        }
                    )
        for row in reminders:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "pending")).strip().lower()
            if status == "completed":
                continue
            due_at = _as_float(row.get("due_at", row.get("due", now + 1_000_000)), now + 1_000_000)
            if due_at < now:
                anomalies.append(
                    {
                        "type": "missed_reminder",
                        "text": str(row.get("text", "reminder")).strip(),
                        "severity": "medium",
                    }
                )
        payload = {
            "action": action,
            "anomaly_count": len(anomalies),
            "notify": len(anomalies) > 0,
            "anomalies": anomalies,
        }
        effect = "anomalies_detected" if anomalies else "no_anomalies"
        record_summary("proactive_assistant", "ok", start_time, effect=effect, risk="medium" if anomalies else "low")
        return _expansion_payload_response(payload)

    if action == "nudge_decision":
        candidates = args.get("candidates") if isinstance(args.get("candidates"), list) else []
        max_dispatch = _as_int(args.get("max_dispatch", 5), 5, minimum=1, maximum=50)
        now = _as_float(args.get("now", time.time()), time.time(), minimum=0.0)
        dedupe_window_sec = _as_float(args.get("dedupe_window_sec", 600.0), 600.0, minimum=0.0, maximum=86_400.0)
        policy = _normalize_nudge_policy(args.get("policy", _nudge_policy))
        context = args.get("context") if isinstance(args.get("context"), dict) else {}
        user_busy = _as_bool(context.get("user_busy"), default=False)
        conversation_active = _as_bool(context.get("conversation_active"), default=False)
        presence_confidence = _as_float(
            context.get("presence_confidence", 1.0),
            1.0,
            minimum=0.0,
            maximum=1.0,
        )
        quiet_override = args.get("quiet_window_active")
        if isinstance(quiet_override, bool):
            quiet_active = quiet_override
        else:
            quiet_active = _quiet_window_active(now_ts=now)
        recent_dispatches = _prune_recent_dispatches(
            _proactive_state.get("nudge_recent_dispatches", []),
            now_ts=now,
            dedupe_window_sec=dedupe_window_sec,
            max_entries=NUDGE_RECENT_DISPATCH_MAX,
        )
        dedupe_suppressed = 0

        interrupt_rows: list[dict[str, Any]] = []
        notify_rows: list[dict[str, Any]] = []
        defer_rows: list[dict[str, Any]] = []
        for index, row in enumerate(candidates):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("text") or row.get("task") or f"candidate-{index}").strip()
            if not title:
                title = f"candidate-{index}"
            severity, severity_rank = _nudge_severity(row.get("severity"))
            due_at = _as_float(row.get("due_at", 0.0), 0.0, minimum=0.0)
            expires_at = _as_float(row.get("expires_at", 0.0), 0.0, minimum=0.0)
            overdue_sec = max(0.0, now - due_at) if due_at > 0.0 else 0.0
            due_soon_sec = max(0.0, due_at - now) if due_at > 0.0 else 0.0
            bucket, reason = _nudge_bucket(
                policy=policy,
                quiet_active=quiet_active,
                severity_rank=severity_rank,
                overdue_sec=overdue_sec,
                due_soon_sec=due_soon_sec,
            )
            if expires_at > 0.0 and expires_at < now:
                bucket = "defer"
                reason = "expired"
            if bucket == "interrupt" and not _as_bool(row.get("interrupt_allowed"), default=True):
                bucket = "notify" if not quiet_active else "defer"
                reason = "interrupt_not_allowed"
            if bucket == "interrupt":
                if conversation_active and severity_rank < 4 and overdue_sec < 1800.0:
                    bucket = "notify" if not quiet_active else "defer"
                    reason = "context_conversation_active"
                elif user_busy and severity_rank < 4 and overdue_sec < 1200.0:
                    bucket = "notify" if not quiet_active else "defer"
                    reason = "context_user_busy"
                elif presence_confidence < 0.35 and severity_rank < 4:
                    bucket = "notify" if not quiet_active else "defer"
                    reason = "context_low_presence_confidence"
            source = str(row.get("source", "unknown")).strip() or "unknown"
            fingerprint = _nudge_fingerprint(
                row=row,
                title=title,
                severity=severity,
                source=source,
            )
            if bucket in {"interrupt", "notify"} and _has_recent_dispatch(
                recent_dispatches,
                fingerprint=fingerprint,
                now_ts=now,
                dedupe_window_sec=dedupe_window_sec,
            ):
                bucket = "defer"
                reason = "duplicate_recent_dispatch"
                dedupe_suppressed += 1
            item = {
                "id": str(row.get("id", f"nudge-{index}")).strip() or f"nudge-{index}",
                "title": title,
                "severity": severity,
                "source": source,
                "overdue_sec": overdue_sec,
                "due_soon_sec": due_soon_sec,
                "score": _nudge_row_score(
                    severity_rank=severity_rank,
                    overdue_sec=overdue_sec,
                    due_soon_sec=due_soon_sec,
                ),
                "bucket": bucket,
                "reason": reason,
                "_fingerprint": fingerprint,
            }
            if bucket == "interrupt":
                interrupt_rows.append(item)
            elif bucket == "notify":
                notify_rows.append(item)
            else:
                defer_rows.append(item)

        interrupt_rows.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
        notify_rows.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
        defer_rows.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
        dispatch_rows = interrupt_rows + notify_rows
        overflow = dispatch_rows[max_dispatch:]
        dispatch_rows = dispatch_rows[:max_dispatch]
        if overflow:
            for row in overflow:
                row["bucket"] = "defer"
                row["reason"] = "dispatch_capacity"
            defer_rows.extend(overflow)
        interrupt = [row for row in dispatch_rows if str(row.get("bucket", "")) == "interrupt"]
        notify = [row for row in dispatch_rows if str(row.get("bucket", "")) == "notify"]
        for row in interrupt + notify:
            _record_recent_dispatch(
                recent_dispatches,
                fingerprint=str(row.get("_fingerprint", "")),
                dispatched_at=now,
            )
        recent_dispatches = _prune_recent_dispatches(
            recent_dispatches,
            now_ts=now,
            dedupe_window_sec=dedupe_window_sec,
            max_entries=NUDGE_RECENT_DISPATCH_MAX,
        )
        for row in interrupt:
            row.pop("bucket", None)
            row.pop("_fingerprint", None)
        for row in notify:
            row.pop("bucket", None)
            row.pop("_fingerprint", None)
        for row in defer_rows:
            row.pop("bucket", None)
            row.pop("_fingerprint", None)

        _proactive_state["nudge_decisions_total"] = int(_proactive_state.get("nudge_decisions_total", 0) or 0) + 1
        _proactive_state["nudge_interrupt_total"] = int(_proactive_state.get("nudge_interrupt_total", 0) or 0) + len(interrupt)
        _proactive_state["nudge_notify_total"] = int(_proactive_state.get("nudge_notify_total", 0) or 0) + len(notify)
        _proactive_state["nudge_defer_total"] = int(_proactive_state.get("nudge_defer_total", 0) or 0) + len(defer_rows)
        _proactive_state["nudge_deduped_total"] = int(_proactive_state.get("nudge_deduped_total", 0) or 0) + dedupe_suppressed
        _proactive_state["last_nudge_decision_at"] = now
        if dedupe_suppressed > 0:
            _proactive_state["last_nudge_dedupe_at"] = now
        _proactive_state["nudge_recent_dispatches"] = recent_dispatches

        payload = {
            "action": action,
            "policy": policy,
            "quiet_window_active": quiet_active,
            "context": {
                "user_busy": user_busy,
                "conversation_active": conversation_active,
                "presence_confidence": presence_confidence,
            },
            "candidate_count": len(candidates),
            "dispatch_count": len(dispatch_rows),
            "interrupt_count": len(interrupt),
            "notify_count": len(notify),
            "defer_count": len(defer_rows),
            "dedupe_window_sec": dedupe_window_sec,
            "dedupe_suppressed_count": dedupe_suppressed,
            "reason_counts": _nudge_reason_counts(
                interrupt=interrupt,
                notify=notify,
                defer=defer_rows,
            ),
            "interrupt": interrupt,
            "notify": notify,
            "defer": defer_rows,
            "counters": {
                "nudge_decisions_total": int(_proactive_state.get("nudge_decisions_total", 0) or 0),
                "nudge_interrupt_total": int(_proactive_state.get("nudge_interrupt_total", 0) or 0),
                "nudge_notify_total": int(_proactive_state.get("nudge_notify_total", 0) or 0),
                "nudge_defer_total": int(_proactive_state.get("nudge_defer_total", 0) or 0),
                "nudge_deduped_total": int(_proactive_state.get("nudge_deduped_total", 0) or 0),
                "last_nudge_decision_at": float(_proactive_state.get("last_nudge_decision_at", 0.0) or 0.0),
                "last_nudge_dedupe_at": float(_proactive_state.get("last_nudge_dedupe_at", 0.0) or 0.0),
                "nudge_recent_dispatch_count": len(recent_dispatches),
            },
        }
        risk = "medium" if interrupt else ("low" if not notify else "medium")
        record_summary(
            "proactive_assistant",
            "ok",
            start_time,
            effect=f"nudge_dispatch={len(dispatch_rows)}",
            risk=risk,
        )
        return _expansion_payload_response(payload)

    if action == "routine_suggestions":
        if not _as_bool(args.get("opt_in"), default=False):
            _record_service_error("proactive_assistant", start_time, "policy")
            return {"content": [{"type": "text", "text": "Routine suggestions require opt_in=true."}]}
        history = args.get("history") if isinstance(args.get("history"), list) else []
        counts: dict[str, int] = {}
        for row in history:
            if isinstance(row, dict):
                key = str(row.get("action") or row.get("name") or "").strip().lower()
            else:
                key = str(row).strip().lower()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        suggestions = [
            {
                "suggestion": f"Automate '{name}' as a routine trigger.",
                "occurrences": count,
            }
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if count >= 3
        ][:10]
        payload = {
            "action": action,
            "opt_in": True,
            "suggestion_count": len(suggestions),
            "suggestions": suggestions,
        }
        record_summary("proactive_assistant", "ok", start_time, effect=f"suggestions={len(suggestions)}", risk="low")
        return _expansion_payload_response(payload)

    if action == "follow_through":
        pending = args.get("pending_actions") if isinstance(args.get("pending_actions"), list) else []
        for row in pending:
            if not isinstance(row, dict):
                continue
            _proactive_state["pending_follow_through"].append(
                {
                    "created_at": now,
                    "task": str(row.get("task") or row.get("action") or "").strip(),
                    "payload": {str(k): v for k, v in row.items()},
                }
            )
        executed: dict[str, Any] | None = None
        if _as_bool(args.get("confirm"), default=False) and _proactive_state["pending_follow_through"]:
            executed = _proactive_state["pending_follow_through"].pop(0)
            executed["executed_at"] = now
        payload = {
            "action": action,
            "queue_size": len(_proactive_state["pending_follow_through"]),
            "executed": executed,
        }
        record_summary("proactive_assistant", "ok", start_time, effect="follow_through", risk="low")
        return _expansion_payload_response(payload)

    if action == "event_digest":
        snooze_minutes = _as_int(args.get("snooze_minutes", 0), 0, minimum=0, maximum=24 * 60)
        if snooze_minutes > 0:
            _proactive_state["digest_snoozed_until"] = now + (snooze_minutes * 60.0)
        snoozed_until = float(_proactive_state.get("digest_snoozed_until", 0.0) or 0.0)
        digest_items = args.get("digest_items") if isinstance(args.get("digest_items"), list) else []
        _proactive_state["last_digest_at"] = now
        if snoozed_until > now:
            payload = {
                "action": action,
                "status": "snoozed",
                "snoozed_until": snoozed_until,
                "remaining_sec": max(0.0, snoozed_until - now),
            }
            record_summary("proactive_assistant", "ok", start_time, effect="digest_snoozed", risk="low")
            return _expansion_payload_response(payload)
        payload = {
            "action": action,
            "status": "ready",
            "digest_count": len(digest_items),
            "digest_items": digest_items[:20],
            "snoozed_until": snoozed_until,
        }
        record_summary("proactive_assistant", "ok", start_time, effect="digest_ready", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("proactive_assistant", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown proactive_assistant action."}]}


async def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
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
    return {"content": [{"type": "text", "text": f"Memory stored (id={memory_id}, scope={scope})."}]}


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


async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _as_float = s._as_float
    _config = s._config
    _as_bool = s._as_bool
    _as_str_list = s._as_str_list
    _memory_requested_scopes = s._memory_requested_scopes
    _memory_entry_scope = s._memory_entry_scope
    _memory_visible_tags = s._memory_visible_tags
    _memory_confidence_score = s._memory_confidence_score
    _memory_confidence_label = s._memory_confidence_label
    _memory_source_trail = s._memory_source_trail

    start_time = time.monotonic()
    if not _tool_permitted("memory_search"):
        record_summary("memory_search", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_search", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    query = str(args.get("query", "")).strip()
    if not query:
        _record_service_error("memory_search", start_time, "missing_query")
        return {"content": [{"type": "text", "text": "Search query required."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    default_max_sensitivity = _as_float(
        getattr(_config, "memory_max_sensitivity", 0.4),
        0.4,
        minimum=0.0,
        maximum=1.0,
    )
    default_hybrid_weight = _as_float(
        getattr(_config, "memory_hybrid_weight", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    default_decay_enabled = _as_bool(getattr(_config, "memory_decay_enabled", False), default=False)
    default_decay_half_life_days = _as_float(
        getattr(_config, "memory_decay_half_life_days", 30.0),
        30.0,
        minimum=0.1,
    )
    default_mmr_enabled = _as_bool(getattr(_config, "memory_mmr_enabled", False), default=False)
    default_mmr_lambda = _as_float(
        getattr(_config, "memory_mmr_lambda", 0.7),
        0.7,
        minimum=0.0,
        maximum=1.0,
    )
    include_sensitive = _as_bool(args.get("include_sensitive"), default=False)
    max_sensitivity = None if include_sensitive else _as_float(
        args.get("max_sensitivity", default_max_sensitivity),
        default_max_sensitivity,
        minimum=0.0,
        maximum=1.0,
    )
    source_list = _as_str_list(args.get("sources"))
    scoped_policy = _memory_requested_scopes(args.get("scopes"), query=query)
    try:
        results = _memory.search_v2(
            query,
            limit=limit,
            max_sensitivity=max_sensitivity,
            hybrid_weight=_as_float(
                args.get("hybrid_weight", default_hybrid_weight),
                default_hybrid_weight,
                minimum=0.0,
                maximum=1.0,
            ),
            decay_enabled=_as_bool(args.get("decay_enabled"), default=default_decay_enabled),
            decay_half_life_days=_as_float(
                args.get("decay_half_life_days", default_decay_half_life_days),
                default_decay_half_life_days,
                minimum=0.1,
            ),
            mmr_enabled=_as_bool(args.get("mmr_enabled"), default=default_mmr_enabled),
            mmr_lambda=_as_float(
                args.get("mmr_lambda", default_mmr_lambda),
                default_mmr_lambda,
                minimum=0.0,
                maximum=1.0,
            ),
            sources=source_list,
        )
    except Exception as e:
        _record_service_error("memory_search", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory search failed: {e}"}]}
    scoped_results = []
    for entry in results:
        if _memory_entry_scope(entry) in scoped_policy:
            scoped_results.append(entry)
        if len(scoped_results) >= limit:
            break
    results = scoped_results
    if not results:
        record_summary("memory_search", "empty", start_time)
        return {"content": [{"type": "text", "text": f"No relevant memories found in scopes={','.join(scoped_policy)}."}]}
    lines = [f"Retrieval policy scopes={','.join(scoped_policy)}"]
    now_ts = time.time()
    for entry in results:
        visible_tags = _memory_visible_tags(entry.tags)
        tags = f" tags={','.join(visible_tags)}" if visible_tags else ""
        snippet = entry.text[:200]
        confidence_score = _memory_confidence_score(entry, now_ts=now_ts)
        confidence_label = _memory_confidence_label(confidence_score)
        source = str(entry.source).strip() or "unknown"
        scope = _memory_entry_scope(entry)
        trail = _memory_source_trail(entry)
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} score={entry.score:.2f} trail={trail} {snippet}{tags}"
        )
    record_summary("memory_search", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_status(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_bool = s._as_bool
    MEMORY_SCOPES = s.MEMORY_SCOPES
    MEMORY_SCOPE_TAG_PREFIX = s.MEMORY_SCOPE_TAG_PREFIX
    MEMORY_QUERY_SCOPE_HINTS = s.MEMORY_QUERY_SCOPE_HINTS
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("memory_status"):
        record_summary("memory_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_status", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    try:
        if _as_bool(args.get("warm"), default=False):
            _memory.warm()
        if _as_bool(args.get("sync"), default=False):
            _memory.sync()
        if _as_bool(args.get("optimize"), default=False):
            _memory.optimize()
        if _as_bool(args.get("vacuum"), default=False):
            _memory.vacuum()
        status = _memory.memory_status()
        if isinstance(status, dict):
            status["confidence_model"] = {
                "version": "v1",
                "inputs": ["retrieval_score", "recency", "source", "sensitivity"],
            }
            status["scope_policy"] = {
                "supported_scopes": sorted(MEMORY_SCOPES),
                "tag_prefix": MEMORY_SCOPE_TAG_PREFIX,
                "query_hints": {scope: sorted(hints) for scope, hints in MEMORY_QUERY_SCOPE_HINTS.items()},
                "default_scope": "preferences",
            }
    except Exception as e:
        _record_service_error("memory_status", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory status failed: {e}"}]}
    record_summary("memory_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status)}]}


async def memory_recent(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _as_str_list = s._as_str_list
    _memory_requested_scopes = s._memory_requested_scopes
    _memory_entry_scope = s._memory_entry_scope
    _memory_visible_tags = s._memory_visible_tags
    _memory_confidence_score = s._memory_confidence_score
    _memory_confidence_label = s._memory_confidence_label
    _memory_source_trail = s._memory_source_trail

    start_time = time.monotonic()
    if not _tool_permitted("memory_recent"):
        record_summary("memory_recent", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_recent", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    kind = args.get("kind")
    source_list = _as_str_list(args.get("sources"))
    scoped_policy = _memory_requested_scopes(args.get("scopes"), query=str(args.get("query", "")))
    try:
        results = _memory.recent(limit=limit, kind=str(kind) if kind else None, sources=source_list)
    except Exception as e:
        _record_service_error("memory_recent", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory recent failed: {e}"}]}
    scoped_results = []
    for entry in results:
        if _memory_entry_scope(entry) in scoped_policy:
            scoped_results.append(entry)
        if len(scoped_results) >= limit:
            break
    results = scoped_results
    if not results:
        record_summary("memory_recent", "empty", start_time)
        return {"content": [{"type": "text", "text": f"No recent memories found in scopes={','.join(scoped_policy)}."}]}
    lines = [f"Retrieval policy scopes={','.join(scoped_policy)}"]
    now_ts = time.time()
    for entry in results:
        visible_tags = _memory_visible_tags(entry.tags)
        tags = f" tags={','.join(visible_tags)}" if visible_tags else ""
        snippet = entry.text[:200]
        confidence_score = _memory_confidence_score(entry, now_ts=now_ts)
        confidence_label = _memory_confidence_label(confidence_score)
        source = str(entry.source).strip() or "unknown"
        scope = _memory_entry_scope(entry)
        trail = _memory_source_trail(entry)
        lines.append(
            f"[{entry.id}] ({entry.kind}) confidence={confidence_label}({confidence_score:.2f}) "
            f"scope={scope} source={source} trail={trail} {snippet}{tags}"
        )
    record_summary("memory_recent", "ok", start_time, effect=f"scopes={','.join(scoped_policy)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def memory_summary_add(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_add"):
        record_summary("memory_summary_add", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_add", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    topic = str(args.get("topic", "")).strip()
    summary = str(args.get("summary", "")).strip()
    if not topic or not summary:
        _record_service_error("memory_summary_add", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "Summary topic and text required."}]}
    try:
        _memory.upsert_summary(topic, summary)
    except Exception as e:
        _record_service_error("memory_summary_add", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary add failed: {e}"}]}
    record_summary("memory_summary_add", "ok", start_time)
    return {"content": [{"type": "text", "text": "Summary stored."}]}


async def memory_summary_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _memory = s._memory
    _record_service_error = s._record_service_error
    _as_int = s._as_int

    start_time = time.monotonic()
    if not _tool_permitted("memory_summary_list"):
        record_summary("memory_summary_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _memory:
        _record_service_error("memory_summary_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Memory store not available."}]}
    limit = _as_int(args.get("limit", 5), 5, minimum=1, maximum=100)
    try:
        results = _memory.list_summaries(limit=limit)
    except Exception as e:
        _record_service_error("memory_summary_list", start_time, "storage_error")
        return {"content": [{"type": "text", "text": f"Memory summary list failed: {e}"}]}
    if not results:
        record_summary("memory_summary_list", "empty", start_time)
        return {"content": [{"type": "text", "text": "No summaries found."}]}
    lines = [f"{summary.topic}: {summary.summary}" for summary in results]
    record_summary("memory_summary_list", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _memory_quality_audit(*, stale_days: float, limit: int) -> dict[str, Any]:
    s = _services()
    time = s.time
    re = s.re
    _memory = s._memory

    if _memory is None:
        return {"error": "missing_store"}
    entries = _memory.recent(limit=limit)
    duplicates: list[dict[str, Any]] = []
    duplicate_ids: list[int] = []
    seen_by_text: dict[str, int] = {}
    stale_ids: list[int] = []
    contradictions: list[dict[str, Any]] = []
    assertions: dict[str, str] = {}
    now = time.time()
    stale_cutoff = now - (max(1.0, stale_days) * 86400.0)
    is_not_re = re.compile(r"^\s*(?P<subject>[a-z0-9 _-]{2,})\s+is\s+not\s+(?P<value>[a-z0-9 _-]{1,80})\s*$", re.IGNORECASE)
    is_re = re.compile(r"^\s*(?P<subject>[a-z0-9 _-]{2,})\s+is\s+(?P<value>[a-z0-9 _-]{1,80})\s*$", re.IGNORECASE)
    for entry in entries:
        text_key = " ".join(str(entry.text).strip().lower().split())
        if text_key:
            prior_id = seen_by_text.get(text_key)
            if prior_id is None:
                seen_by_text[text_key] = int(entry.id)
            else:
                duplicate_ids.append(int(entry.id))
                duplicates.append({"memory_id": int(entry.id), "duplicate_of": int(prior_id)})
        if float(entry.created_at) < stale_cutoff:
            stale_ids.append(int(entry.id))
        text = str(entry.text).strip().lower()
        neg = is_not_re.match(text)
        pos = is_re.match(text)
        if neg:
            key = neg.group("subject").strip()
            value = f"not:{neg.group('value').strip()}"
        elif pos:
            key = pos.group("subject").strip()
            value = f"yes:{pos.group('value').strip()}"
        else:
            key = ""
            value = ""
        if key:
            previous = assertions.get(key)
            if previous is not None and previous != value:
                contradictions.append({"subject": key, "previous": previous, "current": value, "memory_id": int(entry.id)})
            assertions[key] = value
    return {
        "scanned": len(entries),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates[:100],
        "duplicate_ids": duplicate_ids,
        "stale_count": len(stale_ids),
        "stale_ids": stale_ids[:200],
        "contradiction_count": len(contradictions),
        "contradictions": contradictions[:50],
        "stale_days": stale_days,
    }

async def memory_governance(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    suppress = s.suppress
    MEMORY_SCOPES = s.MEMORY_SCOPES
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _identity_default_user = s._identity_default_user
    _as_str_list = s._as_str_list
    _memory_partition_overlays = s._memory_partition_overlays
    _expansion_payload_response = s._expansion_payload_response
    _as_float = s._as_float
    _as_int = s._as_int
    _memory_quality_last = s._memory_quality_last
    _as_bool = s._as_bool
    _memory = s._memory

    start_time = time.monotonic()
    if not _tool_permitted("memory_governance"):
        record_summary("memory_governance", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "partition":
        user = str(args.get("user", _identity_default_user)).strip().lower() or _identity_default_user
        shared_scopes = [scope for scope in _as_str_list(args.get("shared_scopes"), lower=True) if scope in MEMORY_SCOPES]
        private_scopes = [scope for scope in _as_str_list(args.get("private_scopes"), lower=True) if scope in MEMORY_SCOPES]
        if not private_scopes:
            private_scopes = sorted(MEMORY_SCOPES)
        _memory_partition_overlays[user] = {
            "user": user,
            "shared_scopes": sorted(set(shared_scopes)),
            "private_scopes": sorted(set(private_scopes)),
            "updated_at": time.time(),
        }
        payload = {
            "action": action,
            "overlay": dict(_memory_partition_overlays[user]),
            "overlay_count": len(_memory_partition_overlays),
        }
        record_summary("memory_governance", "ok", start_time, effect="partition_updated", risk="low")
        return _expansion_payload_response(payload)

    if action == "quality_audit":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        stale_days = _as_float(args.get("stale_days", 90.0), 90.0, minimum=1.0, maximum=3650.0)
        limit = _as_int(args.get("limit", 300), 300, minimum=10, maximum=1000)
        try:
            report = _memory_quality_audit(stale_days=stale_days, limit=limit)
        except Exception as exc:
            _record_service_error("memory_governance", start_time, "storage_error")
            return {"content": [{"type": "text", "text": f"Memory quality audit failed: {exc}"}]}
        report["action"] = action
        report["generated_at"] = time.time()
        _memory_quality_last.clear()
        _memory_quality_last.update(report)
        record_summary("memory_governance", "ok", start_time, effect="quality_audit", risk="low")
        return _expansion_payload_response(report)

    if action == "cleanup":
        if _memory is None:
            _record_service_error("memory_governance", start_time, "missing_store")
            return {"content": [{"type": "text", "text": "Memory store not available."}]}
        apply = _as_bool(args.get("apply"), default=False)
        duplicate_ids = [int(item) for item in _memory_quality_last.get("duplicate_ids", []) if isinstance(item, int)]
        stale_ids = [int(item) for item in _memory_quality_last.get("stale_ids", []) if isinstance(item, int)]
        candidate_ids = sorted(set(duplicate_ids + stale_ids))
        removed = 0
        if apply:
            for memory_id in candidate_ids:
                with suppress(Exception):
                    if _memory.delete_memory(memory_id):
                        removed += 1
        payload = {
            "action": action,
            "apply": apply,
            "candidate_count": len(candidate_ids),
            "removed_count": removed,
            "candidate_ids": candidate_ids[:200],
        }
        record_summary("memory_governance", "ok", start_time, effect="cleanup_applied" if apply else "cleanup_preview", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("memory_governance", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown memory_governance action."}]}

async def identity_trust(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _runtime_voice_state = s._runtime_voice_state
    _identity_profile_level = s._identity_profile_level
    _expansion_payload_response = s._expansion_payload_response
    _identity_trust_policies = s._identity_trust_policies
    _as_str_list = s._as_str_list
    _guest_sessions = s._guest_sessions
    _resolve_guest_session = s._resolve_guest_session
    _register_guest_session = s._register_guest_session
    _as_bool = s._as_bool
    _household_profiles = s._household_profiles
    GUEST_SESSION_DEFAULT_TTL_SEC = s.GUEST_SESSION_DEFAULT_TTL_SEC

    start_time = time.monotonic()
    if not _tool_permitted("identity_trust"):
        record_summary("identity_trust", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "session_confidence":
        voice_conf = _as_float(args.get("voice_confidence", 0.5), 0.5, minimum=0.0, maximum=1.0)
        operator_hint = str(args.get("operator_hint", "unknown")).strip().lower()
        stt_conf = _as_float(
            (_runtime_voice_state.get("stt_diagnostics", {}) if isinstance(_runtime_voice_state.get("stt_diagnostics"), dict) else {}).get("confidence_score", 0.5),
            0.5,
            minimum=0.0,
            maximum=1.0,
        )
        hint_adjust = {
            "trusted": 0.2,
            "owner": 0.15,
            "known": 0.1,
            "unknown": 0.0,
            "guest": -0.25,
            "untrusted": -0.3,
        }.get(operator_hint, 0.0)
        score = max(0.0, min(1.0, (voice_conf * 0.7) + (stt_conf * 0.2) + hint_adjust))
        band = "high" if score >= 0.8 else "medium" if score >= 0.55 else "low"
        payload = {
            "action": action,
            "identity_confidence": score,
            "band": band,
            "voice_confidence": voice_conf,
            "stt_confidence": stt_conf,
            "operator_hint": operator_hint,
        }
        record_summary("identity_trust", "ok", start_time, effect=f"confidence:{band}", risk="low")
        return _expansion_payload_response(payload)

    if action == "policy_set":
        domain = str(args.get("domain", "")).strip().lower()
        if not domain:
            _record_service_error("identity_trust", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "domain is required for policy_set."}]}
        required_profile = _identity_profile_level(str(args.get("required_profile", "control")))
        requires_step_up = _as_bool(args.get("requires_step_up"), default=False)
        _identity_trust_policies[domain] = {
            "required_profile": required_profile,
            "requires_step_up": requires_step_up,
            "updated_at": time.time(),
        }
        payload = {
            "action": action,
            "domain": domain,
            "policy": dict(_identity_trust_policies[domain]),
            "policy_count": len(_identity_trust_policies),
        }
        record_summary("identity_trust", "ok", start_time, effect=f"policy_set:{domain}", risk="low")
        return _expansion_payload_response(payload)

    if action == "policy_get":
        domain = str(args.get("domain", "")).strip().lower()
        if domain:
            payload = {"action": action, "domain": domain, "policy": dict(_identity_trust_policies.get(domain, {}))}
        else:
            payload = {
                "action": action,
                "policy_count": len(_identity_trust_policies),
                "policies": {name: dict(row) for name, row in sorted(_identity_trust_policies.items())},
            }
        record_summary("identity_trust", "ok", start_time, effect="policy_get", risk="low")
        return _expansion_payload_response(payload)

    if action == "guest_start":
        guest_id = str(args.get("guest_id", "guest")).strip().lower() or "guest"
        ttl_sec = _as_float(args.get("ttl_sec", GUEST_SESSION_DEFAULT_TTL_SEC), GUEST_SESSION_DEFAULT_TTL_SEC)
        capabilities = _as_str_list(args.get("capabilities"), lower=True) or [
            "system_status",
            "get_time",
            "proactive_assistant",
            "integration_hub",
        ]
        row = _register_guest_session(
            guest_id=guest_id,
            capabilities=capabilities,
            ttl_sec=ttl_sec,
        )
        payload = {"action": action, **row, "session_count": len(_guest_sessions)}
        record_summary("identity_trust", "ok", start_time, effect="guest_session_created", risk="low")
        return _expansion_payload_response(payload)

    if action == "guest_validate":
        token = str(args.get("guest_session_token", "")).strip()
        row = _resolve_guest_session(token)
        if row is None:
            _record_service_error("identity_trust", start_time, "not_found")
            return _expansion_payload_response({"action": action, "valid": False})
        payload = {"action": action, "valid": True, **row}
        record_summary("identity_trust", "ok", start_time, effect="guest_session_valid", risk="low")
        return _expansion_payload_response(payload)

    if action == "guest_end":
        token = str(args.get("guest_session_token", "")).strip()
        removed = _guest_sessions.pop(token, None)
        payload = {"action": action, "removed": removed is not None, "session_count": len(_guest_sessions)}
        record_summary("identity_trust", "ok", start_time, effect="guest_session_removed", risk="low")
        return _expansion_payload_response(payload)

    if action == "household_upsert":
        user = str(args.get("user", "")).strip().lower()
        if not user:
            _record_service_error("identity_trust", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "user is required for household_upsert."}]}
        role = str(args.get("role", "member")).strip().lower() or "member"
        trust_level = _identity_profile_level(str(args.get("trust_level", "readonly")))
        exceptions = sorted(set(_as_str_list(args.get("exceptions"), lower=True)))
        _household_profiles[user] = {
            "user": user,
            "role": role,
            "trust_level": trust_level,
            "exceptions": exceptions,
            "updated_at": time.time(),
        }
        payload = {
            "action": action,
            "profile": dict(_household_profiles[user]),
            "profile_count": len(_household_profiles),
        }
        record_summary("identity_trust", "ok", start_time, effect="household_upsert", risk="low")
        return _expansion_payload_response(payload)

    if action == "household_list":
        payload = {
            "action": action,
            "profile_count": len(_household_profiles),
            "profiles": {user: dict(row) for user, row in sorted(_household_profiles.items())},
        }
        record_summary("identity_trust", "ok", start_time, effect="household_list", risk="low")
        return _expansion_payload_response(payload)

    if action == "household_remove":
        user = str(args.get("user", "")).strip().lower()
        removed = _household_profiles.pop(user, None) is not None
        payload = {"action": action, "removed": removed, "profile_count": len(_household_profiles)}
        record_summary("identity_trust", "ok", start_time, effect="household_remove", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("identity_trust", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown identity_trust action."}]}
