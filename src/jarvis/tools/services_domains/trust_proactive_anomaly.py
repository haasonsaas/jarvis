"""Anomaly scan handler for proactive assistant."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def proactive_anomaly_scan(
    args: dict[str, Any],
    *,
    now: float,
    start_time: float,
) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_float = s._as_float
    _expansion_payload_response = s._expansion_payload_response

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
        "action": "anomaly_scan",
        "anomaly_count": len(anomalies),
        "notify": len(anomalies) > 0,
        "anomalies": anomalies,
    }
    effect = "anomalies_detected" if anomalies else "no_anomalies"
    record_summary("proactive_assistant", "ok", start_time, effect=effect, risk="medium" if anomalies else "low")
    return _expansion_payload_response(payload)
