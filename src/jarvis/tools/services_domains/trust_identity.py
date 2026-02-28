"""Identity-trust handlers extracted from trust domain."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

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
                "trust_scores": (
                    {
                        str(user): s._as_float(score, 0.5, minimum=0.0, maximum=1.0)
                        for user, score in s._proactive_state.get("identity_trust_scores", {}).items()
                    }
                    if isinstance(s._proactive_state.get("identity_trust_scores"), dict)
                    else {}
                ),
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
