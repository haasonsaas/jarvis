"""Action handlers for embodiment_presence."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def embodiment_expression_library(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _micro_expression_library = s._micro_expression_library
    _expansion_payload_response = s._expansion_payload_response

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
        "action": "expression_library",
        "library_count": len(_micro_expression_library),
        "library": {key: dict(value) for key, value in sorted(_micro_expression_library.items())},
    }
    record_summary("embodiment_presence", "ok", start_time, effect="expression_library", risk="low")
    return _expansion_payload_response(payload)


async def embodiment_gaze_calibrate(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _record_service_error = s._record_service_error
    _gaze_calibrations = s._gaze_calibrations
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response

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
    payload = {"action": "gaze_calibrate", "calibration": dict(_gaze_calibrations[user]), "calibration_count": len(_gaze_calibrations)}
    record_summary("embodiment_presence", "ok", start_time, effect="gaze_calibrate", risk="low")
    return _expansion_payload_response(payload)


async def embodiment_gesture_profile(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _gesture_envelopes = s._gesture_envelopes
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response

    emotion = str(args.get("emotion", "neutral")).strip().lower() or "neutral"
    importance = str(args.get("importance", "normal")).strip().lower() or "normal"
    key = f"{emotion}:{importance}"
    _gesture_envelopes[key] = {
        "emotion": emotion,
        "importance": importance,
        "amplitude": _as_float(args.get("amplitude", 0.5), 0.5, minimum=0.0, maximum=1.0),
        "updated_at": time.time(),
    }
    payload = {"action": "gesture_profile", "profile_key": key, "profile": dict(_gesture_envelopes[key]), "profile_count": len(_gesture_envelopes)}
    record_summary("embodiment_presence", "ok", start_time, effect="gesture_profile", risk="low")
    return _expansion_payload_response(payload)


async def embodiment_privacy_posture(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _privacy_posture = s._privacy_posture
    _expansion_payload_response = s._expansion_payload_response

    _privacy_posture["state"] = str(args.get("state", "normal")).strip().lower() or "normal"
    _privacy_posture["reason"] = str(args.get("reason", "manual")).strip() or "manual"
    _privacy_posture["updated_at"] = time.time()
    payload = {"action": "privacy_posture", "privacy_posture": dict(_privacy_posture)}
    record_summary("embodiment_presence", "ok", start_time, effect=f"privacy:{_privacy_posture['state']}", risk="low")
    return _expansion_payload_response(payload)


async def embodiment_safety_envelope(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _motion_safety_envelope = s._motion_safety_envelope
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response

    _motion_safety_envelope["proximity_limit_cm"] = _as_float(
        args.get("proximity_limit_cm", _motion_safety_envelope.get("proximity_limit_cm", 35.0)),
        _as_float(_motion_safety_envelope.get("proximity_limit_cm", 35.0), 35.0),
        minimum=5.0,
        maximum=300.0,
    )
    _motion_safety_envelope["hardware_state"] = str(args.get("hardware_state", _motion_safety_envelope.get("hardware_state", "normal"))).strip().lower() or "normal"
    _motion_safety_envelope["updated_at"] = time.time()
    payload = {"action": "safety_envelope", "motion_safety_envelope": dict(_motion_safety_envelope)}
    record_summary("embodiment_presence", "ok", start_time, effect="safety_envelope", risk="low")
    return _expansion_payload_response(payload)


async def embodiment_status(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    _expansion_snapshot = s._expansion_snapshot
    _expansion_payload_response = s._expansion_payload_response

    payload = _expansion_snapshot()["embodiment_presence"]
    payload["action"] = "status"
    record_summary("embodiment_presence", "ok", start_time, effect="status", risk="low")
    return _expansion_payload_response(payload)
