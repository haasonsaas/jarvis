"""Proactive/trust/memory-governance domain handlers extracted from services.py."""

from __future__ import annotations

from typing import Any


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
