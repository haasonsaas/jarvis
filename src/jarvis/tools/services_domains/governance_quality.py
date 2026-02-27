"""Quality and embodiment governance handlers."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

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

