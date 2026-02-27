"""Skills/quality/embodiment domain handlers extracted from services.py."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


def _skills_snapshot_rows() -> list[dict[str, Any]]:
    s = _services()
    _skills_status_snapshot = s._skills_status_snapshot
    snapshot = _skills_status_snapshot()
    rows = snapshot.get("skills") if isinstance(snapshot, dict) else None
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


async def tool_summary(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    list_summaries = s.list_summaries
    _record_service_error = s._record_service_error
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("tool_summary"):
        record_summary("tool_summary", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
    except Exception as e:
        _record_service_error("tool_summary", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(summaries, default=str)}]}


async def tool_summary_text(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    list_summaries = s.list_summaries
    _format_tool_summaries = s._format_tool_summaries
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("tool_summary_text"):
        record_summary("tool_summary_text", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 6), 6, minimum=1, maximum=100)
    try:
        summaries = list_summaries(limit)
        text = _format_tool_summaries(summaries)
    except Exception as e:
        _record_service_error("tool_summary_text", start_time, "summary_unavailable")
        return {"content": [{"type": "text", "text": f"Tool summaries unavailable: {e}"}]}
    record_summary("tool_summary_text", "ok", start_time)
    return {"content": [{"type": "text", "text": text}]}

async def skills_governance(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    Path = s.Path
    suppress = s.suppress
    json = s.json
    hashlib = s.hashlib
    hmac = s.hmac
    SKILL_SANDBOX_TEMPLATES = s.SKILL_SANDBOX_TEMPLATES
    _tool_permitted = s._tool_permitted
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response
    _record_service_error = s._record_service_error
    _skill_quotas = s._skill_quotas
    _as_int = s._as_int
    _as_float = s._as_float
    _config = s._config

    start_time = time.monotonic()
    if not _tool_permitted("skills_governance"):
        record_summary("skills_governance", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "negotiate":
        requested = sorted(set(_as_str_list(args.get("requested_capabilities"), lower=True)))
        candidates: list[dict[str, Any]] = []
        for row in _skills_snapshot_rows():
            if not bool(row.get("enabled")):
                continue
            capabilities = {item.strip().lower() for item in _as_str_list(row.get("capabilities"), lower=True)}
            if requested and not set(requested).issubset(capabilities):
                continue
            score = (len(capabilities.intersection(requested)) * 10) + len(capabilities)
            candidates.append(
                {
                    "name": str(row.get("name", "")),
                    "namespace": str(row.get("namespace", "")),
                    "capabilities": sorted(capabilities),
                    "score": score,
                }
            )
        candidates.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
        payload = {
            "action": action,
            "requested_capabilities": requested,
            "candidate_count": len(candidates),
            "selected": candidates[0] if candidates else None,
            "candidates": candidates[:10],
        }
        record_summary("skills_governance", "ok", start_time, effect="negotiate", risk="low")
        return _expansion_payload_response(payload)

    if action == "dependency_health":
        rows = _skills_snapshot_rows()
        loaded_names = {str(row.get("name", "")).strip().lower() for row in rows}
        health_rows: list[dict[str, Any]] = []
        for row in rows:
            source_path = str(row.get("source_path", "")).strip()
            dependencies: list[str] = []
            if source_path:
                with suppress(Exception):
                    manifest = json.loads(Path(source_path).read_text())
                    dependencies = _as_str_list((manifest if isinstance(manifest, dict) else {}).get("dependencies"), lower=True)
            missing = [dep for dep in dependencies if dep not in loaded_names]
            health_rows.append(
                {
                    "name": str(row.get("name", "")),
                    "dependencies": dependencies,
                    "missing_dependencies": missing,
                    "status": "degraded" if missing else "healthy",
                }
            )
        payload = {"action": action, "skills": health_rows, "degraded_count": sum(1 for row in health_rows if row["status"] != "healthy")}
        record_summary("skills_governance", "ok", start_time, effect="dependency_health", risk="low")
        return _expansion_payload_response(payload)

    if action == "quota_set":
        name = str(args.get("name", "")).strip().lower()
        if not name:
            _record_service_error("skills_governance", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "name is required for quota_set."}]}
        _skill_quotas[name] = {
            "rate_per_min": _as_int(args.get("rate_per_min", 60), 60, minimum=1, maximum=10_000),
            "cpu_sec": _as_float(args.get("cpu_sec", 15.0), 15.0, minimum=0.1, maximum=3600.0),
            "outbound_calls": _as_int(args.get("outbound_calls", 100), 100, minimum=0, maximum=100_000),
            "updated_at": time.time(),
        }
        payload = {"action": action, "name": name, "quota": dict(_skill_quotas[name]), "quota_count": len(_skill_quotas)}
        record_summary("skills_governance", "ok", start_time, effect="quota_set", risk="low")
        return _expansion_payload_response(payload)

    if action == "quota_get":
        name = str(args.get("name", "")).strip().lower()
        if name:
            payload = {"action": action, "name": name, "quota": dict(_skill_quotas.get(name, {}))}
        else:
            payload = {"action": action, "quota_count": len(_skill_quotas), "quotas": {k: dict(v) for k, v in sorted(_skill_quotas.items())}}
        record_summary("skills_governance", "ok", start_time, effect="quota_get", risk="low")
        return _expansion_payload_response(payload)

    if action == "quota_check":
        name = str(args.get("name", "")).strip().lower()
        usage = args.get("usage") if isinstance(args.get("usage"), dict) else {}
        quota = _skill_quotas.get(name, {})
        violations: list[str] = []
        if quota:
            if _as_int(usage.get("rate_per_min", 0), 0) > int(quota.get("rate_per_min", 0)):
                violations.append("rate_per_min")
            if _as_float(usage.get("cpu_sec", 0.0), 0.0) > float(quota.get("cpu_sec", 0.0)):
                violations.append("cpu_sec")
            if _as_int(usage.get("outbound_calls", 0), 0) > int(quota.get("outbound_calls", 0)):
                violations.append("outbound_calls")
        payload = {
            "action": action,
            "name": name,
            "quota_found": bool(quota),
            "allowed": not violations,
            "violations": violations,
            "usage": usage,
            "quota": dict(quota),
        }
        record_summary("skills_governance", "ok", start_time, effect="quota_check", risk="low")
        return _expansion_payload_response(payload)

    if action == "harness_run":
        fixtures = args.get("fixtures") if isinstance(args.get("fixtures"), list) else []
        passed = 0
        failed = 0
        results: list[dict[str, Any]] = []
        for idx, row in enumerate(fixtures):
            if not isinstance(row, dict):
                failed += 1
                results.append({"index": idx, "status": "failed", "reason": "invalid_fixture"})
                continue
            expected = str(row.get("expected", "")).strip()
            actual = str(row.get("actual", "")).strip()
            name = str(row.get("name", f"fixture-{idx}")).strip()
            if expected and expected in actual:
                passed += 1
                results.append({"name": name, "status": "passed"})
            else:
                failed += 1
                results.append({"name": name, "status": "failed", "expected": expected})
        payload = {"action": action, "fixture_count": len(fixtures), "passed": passed, "failed": failed, "results": results[:200]}
        record_summary("skills_governance", "ok", start_time, effect=f"harness_passed={passed}", risk="low")
        return _expansion_payload_response(payload)

    if action == "bundle_sign":
        bundle = args.get("bundle") if isinstance(args.get("bundle"), dict) else {}
        normalized = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        signature = ""
        signed = False
        if _config is not None and str(_config.skills_signature_key).strip():
            signature = hmac.new(str(_config.skills_signature_key).encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
            signed = True
        payload = {
            "action": action,
            "signed": signed,
            "digest": digest,
            "signature": signature,
            "integrity": "hmac-sha256" if signed else "sha256-only",
        }
        record_summary("skills_governance", "ok", start_time, effect="bundle_sign", risk="low")
        return _expansion_payload_response(payload)

    if action == "sandbox_template":
        template = str(args.get("template", "")).strip().lower()
        if template:
            payload = {"action": action, "template": template, "config": dict(SKILL_SANDBOX_TEMPLATES.get(template, {}))}
        else:
            payload = {"action": action, "templates": {name: dict(cfg) for name, cfg in SKILL_SANDBOX_TEMPLATES.items()}}
        record_summary("skills_governance", "ok", start_time, effect="sandbox_template", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("skills_governance", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown skills_governance action."}]}

async def quality_evaluator(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    suppress = s.suppress
    list_summaries = s.list_summaries
    _tool_permitted = s._tool_permitted
    _as_str_list = s._as_str_list
    _as_bool = s._as_bool
    _expansion_payload_response = s._expansion_payload_response
    _record_service_error = s._record_service_error
    _write_quality_report_artifact = s._write_quality_report_artifact
    _append_quality_report = s._append_quality_report
    _as_int = s._as_int
    _quality_reports = s._quality_reports
    _quality_reports_snapshot = s._quality_reports_snapshot

    start_time = time.monotonic()
    if not _tool_permitted("quality_evaluator"):
        record_summary("quality_evaluator", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "weekly_report":
        wins = _as_str_list(args.get("wins"))
        regressions = _as_str_list(args.get("regressions"))
        summaries: list[dict[str, Any]] = []
        with suppress(Exception):
            loaded = list_summaries(300)
            if isinstance(loaded, list):
                summaries = [dict(row) for row in loaded if isinstance(row, dict)]
        error_rows = [row for row in summaries if isinstance(row, dict) and str(row.get("status", "")).strip().lower() in {"error", "failed"}]
        success_rows = [row for row in summaries if isinstance(row, dict) and str(row.get("status", "")).strip().lower() in {"ok", "success"}]
        report = {
            "generated_at": time.time(),
            "errors": len(error_rows),
            "successes": len(success_rows),
            "wins": wins,
            "regressions": regressions,
            "top_failures": [str(row.get("name", "unknown")) for row in error_rows[:10]],
            "notes": "Weekly assistant quality report artifact.",
        }
        artifact_path = _write_quality_report_artifact(report, report_path=str(args.get("report_path", "")).strip() or None)
        report["artifact_path"] = artifact_path
        _append_quality_report(report)
        record_summary("quality_evaluator", "ok", start_time, effect="weekly_report", risk="low")
        return _expansion_payload_response({"action": action, **report})

    if action == "dataset_run":
        dataset = args.get("dataset") if isinstance(args.get("dataset"), list) else []
        strict = _as_bool(args.get("strict"), default=False)
        passed = 0
        failed = 0
        rows: list[dict[str, Any]] = []
        for idx, row in enumerate(dataset):
            if not isinstance(row, dict):
                failed += 1
                rows.append({"index": idx, "status": "failed", "reason": "invalid_case"})
                continue
            name = str(row.get("name", f"case-{idx}")).strip() or f"case-{idx}"
            expected = _as_str_list(row.get("expected_contains"))
            actual = str(row.get("actual", "")).strip()
            ok = all(item in actual for item in expected) if expected else bool(actual)
            if ok:
                passed += 1
            else:
                failed += 1
            rows.append({"name": name, "status": "passed" if ok else "failed", "expected_contains": expected})
        payload = {
            "action": action,
            "strict": strict,
            "case_count": len(dataset),
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / len(dataset)) if dataset else 0.0,
            "accepted": (failed == 0) if strict else (passed >= failed),
            "results": rows[:300],
        }
        record_summary("quality_evaluator", "ok", start_time, effect=f"dataset_passed={passed}", risk="low")
        return _expansion_payload_response(payload)

    if action == "reports_list":
        limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
        payload = {"action": action, "count": len(_quality_reports), "reports": _quality_reports_snapshot(limit=limit)}
        record_summary("quality_evaluator", "ok", start_time, effect="reports_list", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("quality_evaluator", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown quality_evaluator action."}]}

async def embodiment_presence(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _micro_expression_library = s._micro_expression_library
    _gaze_calibrations = s._gaze_calibrations
    _gesture_envelopes = s._gesture_envelopes
    _as_float = s._as_float
    _privacy_posture = s._privacy_posture
    _expansion_payload_response = s._expansion_payload_response
    _motion_safety_envelope = s._motion_safety_envelope
    _expansion_snapshot = s._expansion_snapshot

    start_time = time.monotonic()
    if not _tool_permitted("embodiment_presence"):
        record_summary("embodiment_presence", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "expression_library":
        intent = str(args.get("intent", "")).strip().lower()
        micro_expression = str(args.get("micro_expression", "")).strip().lower()
        certainty_band = str(args.get("certainty_band", "medium")).strip().lower() or "medium"
        if intent and micro_expression:
            _micro_expression_library[intent] = {
                "intent": intent,
                "micro_expression": micro_expression,
                "certainty_band": certainty_band,
                "updated_at": time.time(),
            }
        payload = {
            "action": action,
            "library_count": len(_micro_expression_library),
            "library": {key: dict(value) for key, value in sorted(_micro_expression_library.items())},
        }
        record_summary("embodiment_presence", "ok", start_time, effect="expression_library", risk="low")
        return _expansion_payload_response(payload)

    if action == "gaze_calibrate":
        user = str(args.get("user", "")).strip().lower()
        if not user:
            _record_service_error("embodiment_presence", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "user is required for gaze_calibrate."}]}
        _gaze_calibrations[user] = {
            "user": user,
            "distance_cm": _as_float(args.get("distance_cm", 60.0), 60.0, minimum=20.0, maximum=300.0),
            "seat_offset_deg": _as_float(args.get("seat_offset_deg", 0.0), 0.0, minimum=-45.0, maximum=45.0),
            "updated_at": time.time(),
        }
        payload = {"action": action, "calibration": dict(_gaze_calibrations[user]), "calibration_count": len(_gaze_calibrations)}
        record_summary("embodiment_presence", "ok", start_time, effect="gaze_calibrate", risk="low")
        return _expansion_payload_response(payload)

    if action == "gesture_profile":
        emotion = str(args.get("emotion", "neutral")).strip().lower() or "neutral"
        importance = str(args.get("importance", "normal")).strip().lower() or "normal"
        key = f"{emotion}:{importance}"
        _gesture_envelopes[key] = {
            "emotion": emotion,
            "importance": importance,
            "amplitude": _as_float(args.get("amplitude", 0.5), 0.5, minimum=0.0, maximum=1.0),
            "updated_at": time.time(),
        }
        payload = {"action": action, "profile_key": key, "profile": dict(_gesture_envelopes[key]), "profile_count": len(_gesture_envelopes)}
        record_summary("embodiment_presence", "ok", start_time, effect="gesture_profile", risk="low")
        return _expansion_payload_response(payload)

    if action == "privacy_posture":
        _privacy_posture["state"] = str(args.get("state", "normal")).strip().lower() or "normal"
        _privacy_posture["reason"] = str(args.get("reason", "manual")).strip() or "manual"
        _privacy_posture["updated_at"] = time.time()
        payload = {"action": action, "privacy_posture": dict(_privacy_posture)}
        record_summary("embodiment_presence", "ok", start_time, effect=f"privacy:{_privacy_posture['state']}", risk="low")
        return _expansion_payload_response(payload)

    if action == "safety_envelope":
        _motion_safety_envelope["proximity_limit_cm"] = _as_float(
            args.get("proximity_limit_cm", _motion_safety_envelope.get("proximity_limit_cm", 35.0)),
            _as_float(_motion_safety_envelope.get("proximity_limit_cm", 35.0), 35.0),
            minimum=5.0,
            maximum=300.0,
        )
        _motion_safety_envelope["hardware_state"] = str(args.get("hardware_state", _motion_safety_envelope.get("hardware_state", "normal"))).strip().lower() or "normal"
        _motion_safety_envelope["updated_at"] = time.time()
        payload = {"action": action, "motion_safety_envelope": dict(_motion_safety_envelope)}
        record_summary("embodiment_presence", "ok", start_time, effect="safety_envelope", risk="low")
        return _expansion_payload_response(payload)

    if action == "status":
        payload = _expansion_snapshot()["embodiment_presence"]
        payload["action"] = action
        record_summary("embodiment_presence", "ok", start_time, effect="status", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("embodiment_presence", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown embodiment_presence action."}]}


async def skills_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    suppress = s.suppress
    set_runtime_skills_state = s.set_runtime_skills_state
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("skills_list"):
        record_summary("skills_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    with suppress(Exception):
        _skill_registry.discover()
        set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(_skill_registry.status_snapshot(), default=str)}]}


async def skills_enable(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    set_runtime_skills_state = s.set_runtime_skills_state
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("skills_enable"):
        record_summary("skills_enable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_enable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_enable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.enable_skill(name)
    if not ok:
        _record_service_error("skills_enable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to enable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_enable", "ok", start_time)
    _audit("skills_enable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Enabled skill '{name}'."}]}


async def skills_disable(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    set_runtime_skills_state = s.set_runtime_skills_state
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("skills_disable"):
        record_summary("skills_disable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_disable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_disable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.disable_skill(name)
    if not ok:
        _record_service_error("skills_disable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to disable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_disable", "ok", start_time)
    _audit("skills_disable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Disabled skill '{name}'."}]}


async def skills_version(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("skills_version"):
        record_summary("skills_version", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_version", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_version", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    version = _skill_registry.skill_version(name)
    if version is None:
        _record_service_error("skills_version", start_time, "not_found")
        return {"content": [{"type": "text", "text": f"Skill '{name}' not found."}]}
    record_summary("skills_version", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps({"name": name, "version": version})}]}


def _tool_policy_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    return {
        "allow_count": len(s._tool_allowlist),
        "deny_count": len(s._tool_denylist),
        "home_permission_profile": s._home_permission_profile,
        "safe_mode_enabled": s._safe_mode_enabled,
        "home_require_confirm_execute": bool(s._home_require_confirm_execute),
        "home_conversation_enabled": bool(s._home_conversation_enabled),
        "home_conversation_permission_profile": s._home_conversation_permission_profile,
        "todoist_permission_profile": s._todoist_permission_profile,
        "notification_permission_profile": s._notification_permission_profile,
        "nudge_policy": s._nudge_policy,
        "nudge_quiet_hours_start": s._nudge_quiet_hours_start,
        "nudge_quiet_hours_end": s._nudge_quiet_hours_end,
        "nudge_quiet_window_active": s._quiet_window_active(),
        "email_permission_profile": s._email_permission_profile,
        "memory_pii_guardrails_enabled": s._memory_pii_guardrails_enabled,
        "identity_enforcement_enabled": s._identity_enforcement_enabled,
        "identity_default_profile": s._identity_default_profile,
        "identity_require_approval": s._identity_require_approval,
        "plan_preview_require_ack": s._plan_preview_require_ack,
    }


def _scorecard_context(
    services_module: Any,
    *,
    recent_tool_limit: int,
) -> dict[str, Any]:
    s = services_module
    memory_status: dict[str, Any] | None = None
    if s._memory is not None:
        try:
            memory_status = s._memory.memory_status()
        except Exception as exc:
            memory_status = {"error": str(exc)}

    try:
        recent_tools = s.list_summaries(limit=recent_tool_limit)
    except Exception as exc:
        recent_tools = {"error": str(exc)}
    identity_status = s._identity_status_snapshot()
    tool_policy_status = _tool_policy_status_snapshot(s)
    observability_status = s._observability_snapshot()
    integrations_status = s._integration_health_snapshot()
    audit_status = s._audit_status()
    health = s._health_rollup(
        config_present=(s._config is not None),
        memory_state=memory_status if isinstance(memory_status, dict) else None,
        recent_tools=recent_tools,
        identity_status=identity_status,
    )
    return {
        "memory_status": memory_status,
        "recent_tools": recent_tools,
        "identity_status": identity_status,
        "tool_policy_status": tool_policy_status,
        "observability_status": observability_status,
        "integrations_status": integrations_status,
        "audit_status": audit_status,
        "health": health,
    }


async def system_status(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _expansion_snapshot = s._expansion_snapshot
    _home_conversation_enabled = s._home_conversation_enabled
    _plan_preview_require_ack = s._plan_preview_require_ack
    _config = s._config
    _jarvis_scorecard_snapshot = s._jarvis_scorecard_snapshot
    SYSTEM_STATUS_CONTRACT_VERSION = s.SYSTEM_STATUS_CONTRACT_VERSION
    _now_local = s._now_local
    _timer_status = s._timer_status
    _reminder_status = s._reminder_status
    _voice_attention_snapshot = s._voice_attention_snapshot
    _turn_timeout_listen_sec = s._turn_timeout_listen_sec
    _turn_timeout_think_sec = s._turn_timeout_think_sec
    _turn_timeout_speak_sec = s._turn_timeout_speak_sec
    _turn_timeout_act_sec = s._turn_timeout_act_sec
    _skills_status_snapshot = s._skills_status_snapshot
    _pending_plan_previews = s._pending_plan_previews
    PLAN_PREVIEW_TTL_SEC = s.PLAN_PREVIEW_TTL_SEC
    _memory_retention_days = s._memory_retention_days
    _audit_retention_days = s._audit_retention_days
    _recovery_journal_status = s._recovery_journal_status
    _dead_letter_queue_status = s._dead_letter_queue_status
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("system_status"):
        record_summary("system_status", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    expansion_status = _expansion_snapshot()
    context = _scorecard_context(s, recent_tool_limit=5)
    memory_status = context["memory_status"]
    recent_tools = context["recent_tools"]
    identity_status = context["identity_status"]
    tool_policy_status = context["tool_policy_status"]
    observability_status = context["observability_status"]
    integrations_status = context["integrations_status"]
    audit_status = context["audit_status"]
    health = context["health"]
    scorecard = _jarvis_scorecard_snapshot(
        recent_tools=recent_tools,
        health=health,
        observability=observability_status,
        identity=identity_status,
        tool_policy=tool_policy_status,
        audit=audit_status,
        integrations=integrations_status,
    )

    status = {
        "schema_version": SYSTEM_STATUS_CONTRACT_VERSION,
        "local_time": _now_local(),
        "home_assistant_configured": bool(_config and _config.has_home_assistant),
        "home_conversation_enabled": bool(_home_conversation_enabled),
        "todoist_configured": bool(_config and str(_config.todoist_api_token).strip()),
        "pushover_configured": bool(
            _config
            and str(_config.pushover_api_token).strip()
            and str(_config.pushover_user_key).strip()
        ),
        "motion_enabled": bool(_config and _config.motion_enabled),
        "home_tools_enabled": bool(_config and _config.home_enabled),
        "memory_enabled": bool(_config and _config.memory_enabled),
        "backchannel_style": _config.backchannel_style if _config else "unknown",
        "persona_style": _config.persona_style if _config else "unknown",
        "tool_policy": tool_policy_status,
        "timers": _timer_status(),
        "reminders": _reminder_status(),
        "voice_attention": _voice_attention_snapshot(),
        "turn_timeouts": {
            "watchdog_enabled": bool(_config and getattr(_config, "watchdog_enabled", False)),
            "listen_sec": _turn_timeout_listen_sec,
            "think_sec": _turn_timeout_think_sec,
            "speak_sec": _turn_timeout_speak_sec,
            "act_sec": _turn_timeout_act_sec,
        },
        "integrations": integrations_status,
        "identity": identity_status,
        "skills": _skills_status_snapshot(),
        "observability": observability_status,
        "scorecard": scorecard,
        "plan_preview": {
            "pending_count": len(_pending_plan_previews),
            "ttl_sec": PLAN_PREVIEW_TTL_SEC,
            "strict_mode": bool(_plan_preview_require_ack),
        },
        "retention_policy": {
            "memory_retention_days": _memory_retention_days,
            "audit_retention_days": _audit_retention_days,
        },
        "recovery_journal": _recovery_journal_status(limit=20),
        "dead_letter_queue": _dead_letter_queue_status(limit=20, status_filter="all"),
        "expansion": expansion_status,
        "memory": memory_status,
        "audit": audit_status,
        "recent_tools": recent_tools,
        "health": health,
    }
    record_summary("system_status", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(status, default=str)}]}


async def system_status_contract(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    SYSTEM_STATUS_CONTRACT_VERSION = s.SYSTEM_STATUS_CONTRACT_VERSION
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("system_status_contract"):
        record_summary("system_status_contract", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    contract = {
        "schema_version": SYSTEM_STATUS_CONTRACT_VERSION,
        "top_level_required": [
            "schema_version",
            "local_time",
            "home_assistant_configured",
            "home_conversation_enabled",
            "todoist_configured",
            "pushover_configured",
            "motion_enabled",
            "home_tools_enabled",
            "memory_enabled",
            "backchannel_style",
            "persona_style",
            "tool_policy",
            "timers",
            "reminders",
            "voice_attention",
            "turn_timeouts",
            "integrations",
            "identity",
            "skills",
            "observability",
            "scorecard",
            "plan_preview",
            "retention_policy",
            "recovery_journal",
            "dead_letter_queue",
            "expansion",
            "memory",
            "audit",
            "recent_tools",
            "health",
        ],
        "tool_policy_required": [
            "allow_count",
            "deny_count",
            "home_permission_profile",
            "safe_mode_enabled",
            "home_require_confirm_execute",
            "home_conversation_enabled",
            "home_conversation_permission_profile",
            "todoist_permission_profile",
            "notification_permission_profile",
            "nudge_policy",
            "nudge_quiet_hours_start",
            "nudge_quiet_hours_end",
            "nudge_quiet_window_active",
            "email_permission_profile",
            "memory_pii_guardrails_enabled",
            "identity_enforcement_enabled",
            "identity_default_profile",
            "identity_require_approval",
            "plan_preview_require_ack",
        ],
        "timers_required": [
            "active_count",
            "next_due_in_sec",
        ],
        "reminders_required": [
            "pending_count",
            "completed_count",
            "due_count",
            "next_due_in_sec",
        ],
        "voice_attention_required": [
            "mode",
            "followup_active",
            "sleeping",
            "active_room",
            "adaptive_silence_timeout_sec",
            "speech_rate_wps",
            "interruption_likelihood",
            "turn_choreography",
            "stt_diagnostics",
            "voice_profile_user",
            "voice_profile",
            "voice_profile_count",
            "acoustic_scene",
            "preference_learning",
            "multimodal_grounding",
        ],
        "voice_attention_acoustic_scene_required": [
            "last_doa_angle",
            "last_doa_speech",
            "last_doa_age_sec",
            "attention_confidence",
            "attention_source",
        ],
        "voice_attention_preference_learning_required": [
            "user",
            "updates",
            "applied_at",
            "source_text",
        ],
        "voice_attention_multimodal_grounding_required": [
            "overall_confidence",
            "confidence_band",
            "attention_source",
            "modality_scores",
            "signals",
            "reasons",
        ],
        "voice_attention_turn_choreography_required": [
            "phase",
            "label",
            "turn_lean",
            "turn_tilt",
            "turn_glance_yaw",
            "updated_at",
        ],
        "voice_attention_stt_diagnostics_required": [
            "source",
            "fallback_used",
            "confidence_score",
            "confidence_band",
            "avg_logprob",
            "avg_no_speech_prob",
            "language",
            "language_probability",
            "segment_count",
            "word_count",
            "char_count",
            "updated_at",
            "error",
        ],
        "voice_attention_voice_profile_required": [
            "verbosity",
            "confirmations",
            "pace",
            "tone",
        ],
        "turn_timeouts_required": [
            "watchdog_enabled",
            "listen_sec",
            "think_sec",
            "speak_sec",
            "act_sec",
        ],
        "integrations_required": [
            "home_assistant",
            "todoist",
            "pushover",
            "weather",
            "webhook",
            "email",
            "channels",
        ],
        "integration_circuit_breaker_required": [
            "open",
            "open_remaining_sec",
            "consecutive_failures",
            "opened_count",
            "cooldown_sec",
            "last_error",
            "last_failure_at",
            "last_success_at",
        ],
        "identity_required": [
            "enabled",
            "default_user",
            "default_profile",
            "require_approval",
            "approval_code_configured",
            "trusted_user_count",
            "trusted_users",
            "profile_count",
            "user_profiles",
            "trust_policy_count",
            "trust_policies",
            "guest_sessions_active",
            "guest_sessions",
            "household_profile_count",
            "household_profiles",
        ],
        "skills_required": [
            "enabled",
            "loaded_count",
            "enabled_count",
            "skills",
        ],
        "observability_required": [
            "enabled",
            "uptime_sec",
            "restart_count",
            "intent_metrics",
            "multimodal_metrics",
            "alerts",
            "latency_dashboards",
            "policy_decision_analytics",
        ],
        "observability_multimodal_metrics_required": [
            "turn_count",
            "avg_confidence",
            "low_confidence_count",
            "low_confidence_rate",
        ],
        "observability_intent_metrics_required": [
            "turn_count",
            "answer_intent_count",
            "action_intent_count",
            "hybrid_intent_count",
            "answer_sample_count",
            "completion_sample_count",
            "answer_quality_success_rate",
            "completion_success_rate",
            "correction_count",
            "correction_frequency",
            "preference_update_turns",
            "preference_update_fields",
        ],
        "observability_latency_dashboards_required": [
            "sample_count",
            "overall_total_ms",
            "by_intent",
            "by_tool_mix",
            "by_wake_mode",
        ],
        "observability_latency_bucket_required": [
            "p50",
            "p95",
            "p99",
        ],
        "observability_policy_decision_analytics_required": [
            "decision_count",
            "by_tool",
            "by_status",
            "by_reason",
            "by_user",
            "by_user_tool",
        ],
        "scorecard_required": [
            "overall",
            "dimensions",
            "weights",
            "computed_at",
        ],
        "scorecard_overall_required": [
            "score",
            "grade",
        ],
        "scorecard_dimensions_required": [
            "latency",
            "reliability",
            "initiative",
            "trust",
        ],
        "scorecard_dimension_required": [
            "score",
            "grade",
        ],
        "plan_preview_required": [
            "pending_count",
            "ttl_sec",
            "strict_mode",
        ],
        "retention_policy_required": [
            "memory_retention_days",
            "audit_retention_days",
        ],
        "recovery_journal_required": [
            "path",
            "exists",
            "entry_count",
            "tracked_actions",
            "unresolved_count",
            "interrupted_count",
            "recent",
        ],
        "dead_letter_queue_required": [
            "path",
            "exists",
            "entry_count",
            "pending_count",
            "failed_count",
            "replayed_count",
            "recent",
        ],
        "expansion_required": [
            "proactive",
            "memory_governance",
            "identity_trust",
            "home_orchestration",
            "skills_governance",
            "planner_engine",
            "quality_evaluator",
            "embodiment_presence",
            "integration_hub",
        ],
        "expansion_proactive_required": [
            "pending_follow_through_count",
            "digest_snoozed_until",
            "last_briefing_at",
            "last_digest_at",
            "nudge_decisions_total",
            "nudge_interrupt_total",
            "nudge_notify_total",
            "nudge_defer_total",
            "nudge_deduped_total",
            "last_nudge_decision_at",
            "last_nudge_dedupe_at",
            "nudge_recent_dispatch_count",
        ],
        "expansion_memory_governance_required": [
            "partition_overlay_count",
            "last_quality_audit",
        ],
        "expansion_identity_trust_required": [
            "trust_policy_count",
            "guest_session_count",
            "household_profile_count",
        ],
        "expansion_home_orchestration_required": [
            "area_policy_count",
            "tracked_task_count",
            "automation_draft_count",
            "automation_applied_count",
        ],
        "expansion_skills_governance_required": [
            "quota_count",
            "sandbox_templates",
        ],
        "expansion_planner_engine_required": [
            "task_graph_count",
            "deferred_action_count",
            "autonomy_task_count",
            "autonomy_waiting_checkpoint_count",
            "autonomy_last_cycle_at",
        ],
        "expansion_quality_evaluator_required": [
            "cached_report_count",
            "recent_reports",
        ],
        "expansion_embodiment_presence_required": [
            "micro_expression_count",
            "gaze_calibration_count",
            "gesture_profile_count",
            "privacy_posture",
            "motion_safety_envelope",
        ],
        "expansion_integration_hub_required": [
            "notes_backend_default",
            "notes_dir",
            "release_channels",
            "active_release_channel",
            "release_channel_config_path",
            "last_release_channel_check_at",
            "last_release_channel_check_channel",
            "last_release_channel_check_passed",
            "migration_checks",
        ],
        "health_required": [
            "health_level",
            "reasons",
        ],
    }
    record_summary("system_status_contract", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(contract)}]}


async def jarvis_scorecard(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _jarvis_scorecard_snapshot = s._jarvis_scorecard_snapshot
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("jarvis_scorecard"):
        record_summary("jarvis_scorecard", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}

    context = _scorecard_context(s, recent_tool_limit=200)
    recent_tools = context["recent_tools"]
    identity_status = context["identity_status"]
    tool_policy_status = context["tool_policy_status"]
    observability_status = context["observability_status"]
    integrations_status = context["integrations_status"]
    audit_status = context["audit_status"]
    health = context["health"]
    scorecard = _jarvis_scorecard_snapshot(
        recent_tools=recent_tools,
        health=health,
        observability=observability_status,
        identity=identity_status,
        tool_policy=tool_policy_status,
        audit=audit_status,
        integrations=integrations_status,
    )
    record_summary("jarvis_scorecard", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(scorecard, default=str)}]}
