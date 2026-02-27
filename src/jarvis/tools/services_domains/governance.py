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
