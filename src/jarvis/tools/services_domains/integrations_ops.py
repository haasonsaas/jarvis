"""Integration operations handlers (weather/webhook/calendar/dead-letter)."""

from __future__ import annotations

import re
import time
from typing import Any

from jarvis.tools.services_domains.integrations_runtime import (
    parse_calendar_window as _runtime_parse_calendar_window,
)


def _services():
    from jarvis.tools import services as s

    return s

async def weather_lookup(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    _tool_permitted = s._tool_permitted
    _integration_circuit_open = s._integration_circuit_open
    _record_service_error = s._record_service_error
    _integration_circuit_open_message = s._integration_circuit_open_message
    _weather_units = s._weather_units
    _effective_act_timeout = s._effective_act_timeout
    _weather_timeout_sec = s._weather_timeout_sec
    _as_exact_int = s._as_exact_int
    _integration_record_success = s._integration_record_success

    start_time = time.monotonic()
    if not _tool_permitted("weather_lookup"):
        record_summary("weather_lookup", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("weather")
    if circuit_open:
        _record_service_error("weather_lookup", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("weather", circuit_remaining)}]}
    location = str(args.get("location", "")).strip()
    if not location:
        _record_service_error("weather_lookup", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "location is required."}]}
    units = str(args.get("units", _weather_units)).strip().lower() or _weather_units
    if units not in {"metric", "imperial"}:
        _record_service_error("weather_lookup", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "units must be metric or imperial."}]}
    geocode_params = {
        "name": location,
        "count": "1",
        "language": "en",
        "format": "json",
    }
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(_weather_timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://geocoding-api.open-meteo.com/v1/search", params=geocode_params) as resp:
                if resp.status != 200:
                    _record_service_error("weather_lookup", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Weather geocoding error ({resp.status})."}]}
                geocode = await resp.json()
            if not isinstance(geocode, dict):
                _record_service_error("weather_lookup", start_time, "invalid_json")
                return {"content": [{"type": "text", "text": "Invalid weather geocoding response."}]}
            results = geocode.get("results")
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                record_summary("weather_lookup", "empty", start_time)
                return {"content": [{"type": "text", "text": f"No weather match found for '{location}'."}]}
            place = results[0]
            latitude = place.get("latitude")
            longitude = place.get("longitude")
            if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                _record_service_error("weather_lookup", start_time, "invalid_json")
                return {"content": [{"type": "text", "text": "Invalid weather geocoding response."}]}
            forecast_params = {
                "latitude": str(float(latitude)),
                "longitude": str(float(longitude)),
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
                "wind_speed_unit": "mph" if units == "imperial" else "kmh",
            }
            async with session.get("https://api.open-meteo.com/v1/forecast", params=forecast_params) as resp:
                if resp.status != 200:
                    _record_service_error("weather_lookup", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Weather forecast error ({resp.status})."}]}
                forecast = await resp.json()
    except asyncio.TimeoutError:
        _record_service_error("weather_lookup", start_time, "timeout")
        return {"content": [{"type": "text", "text": "Weather request timed out."}]}
    except asyncio.CancelledError:
        _record_service_error("weather_lookup", start_time, "cancelled")
        return {"content": [{"type": "text", "text": "Weather request was cancelled."}]}
    except aiohttp.ClientError:
        _record_service_error("weather_lookup", start_time, "network_client_error")
        return {"content": [{"type": "text", "text": "Failed to reach weather provider."}]}
    except Exception:
        _record_service_error("weather_lookup", start_time, "unexpected")
        log.exception("Unexpected weather_lookup failure")
        return {"content": [{"type": "text", "text": "Unexpected weather lookup error."}]}

    if not isinstance(forecast, dict):
        _record_service_error("weather_lookup", start_time, "invalid_json")
        return {"content": [{"type": "text", "text": "Invalid weather forecast response."}]}
    current = forecast.get("current")
    if not isinstance(current, dict):
        _record_service_error("weather_lookup", start_time, "invalid_json")
        return {"content": [{"type": "text", "text": "Invalid weather forecast response."}]}
    temperature = current.get("temperature_2m")
    apparent = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    code = _as_exact_int(current.get("weather_code"))
    code_map = {
        0: "clear",
        1: "mostly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "fog",
        51: "drizzle",
        53: "drizzle",
        55: "drizzle",
        61: "rain",
        63: "rain",
        65: "heavy rain",
        71: "snow",
        73: "snow",
        75: "heavy snow",
        95: "thunderstorm",
    }
    condition = code_map.get(code, "unknown conditions")
    place_name = str(place.get("name", location)).strip() or location
    country = str(place.get("country", "")).strip()
    place_label = f"{place_name}, {country}" if country else place_name
    temp_unit = "F" if units == "imperial" else "C"
    wind_unit = "mph" if units == "imperial" else "km/h"
    _integration_record_success("weather")
    record_summary("weather_lookup", "ok", start_time)
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"{place_label}: {temperature}°{temp_unit}, feels like {apparent}°{temp_unit}, "
                    f"{condition}, humidity {humidity}%, wind {wind} {wind_unit}."
                ),
            }
        ]
    }


async def webhook_trigger(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    asyncio = s.asyncio
    aiohttp = s.aiohttp
    log = s.log
    urlparse = s.urlparse
    _identity_context = s._identity_context
    _tool_permitted = s._tool_permitted
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _integration_circuit_open = s._integration_circuit_open
    _record_service_error = s._record_service_error
    _integration_circuit_open_message = s._integration_circuit_open_message
    _webhook_host_allowed = s._webhook_host_allowed
    _identity_authorize = s._identity_authorize
    _preview_gate = s._preview_gate
    _plan_preview_require_ack = s._plan_preview_require_ack
    _webhook_auth_token = s._webhook_auth_token
    _as_float = s._as_float
    _webhook_timeout_sec = s._webhook_timeout_sec
    _effective_act_timeout = s._effective_act_timeout
    _recovery_operation = s._recovery_operation
    _integration_record_success = s._integration_record_success
    _dead_letter_enqueue = s._dead_letter_enqueue

    start_time = time.monotonic()
    identity_probe = _identity_context(args)
    if not _tool_permitted("webhook_trigger"):
        record_summary("webhook_trigger", "denied", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "policy"},
                identity_probe,
                ["tool=webhook_trigger", "deny:tool_policy"],
            ),
        )
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    circuit_open, circuit_remaining = _integration_circuit_open("webhook")
    if circuit_open:
        _record_service_error("webhook_trigger", start_time, "circuit_open")
        return {"content": [{"type": "text", "text": _integration_circuit_open_message("webhook", circuit_remaining)}]}
    url = str(args.get("url", "")).strip()
    if not url:
        _record_service_error("webhook_trigger", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "url is required."}]}
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "https_required"},
                identity_probe,
                ["tool=webhook_trigger", "deny:https_required"],
            ),
        )
        return {"content": [{"type": "text", "text": "Webhook URL must use https."}]}
    if not _webhook_host_allowed(url):
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "allowlist", "host": parsed.hostname or ""},
                identity_probe,
                ["tool=webhook_trigger", "deny:allowlist"],
            ),
        )
        return {"content": [{"type": "text", "text": "Webhook host is not in WEBHOOK_ALLOWLIST."}]}
    method = str(args.get("method", "POST")).strip().upper() or "POST"
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "method must be one of GET, POST, PUT, PATCH, DELETE."}]}
    payload = args.get("payload")
    if payload is not None and not isinstance(payload, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "payload must be an object when provided."}]}
    headers_raw = args.get("headers")
    if headers_raw is not None and not isinstance(headers_raw, dict):
        _record_service_error("webhook_trigger", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "headers must be an object when provided."}]}
    headers: dict[str, str] = {}
    for key, value in (headers_raw or {}).items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        headers[clean_key] = str(value)
    identity_allowed, identity_message, identity_context, identity_chain = _identity_authorize(
        "webhook_trigger",
        args,
        mutating=True,
        high_risk=True,
    )
    if not identity_allowed:
        _record_service_error("webhook_trigger", start_time, "policy")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "denied", "reason": "identity_policy", "method": method, "host": parsed.hostname or ""},
                identity_context,
                identity_chain,
            ),
        )
        return {"content": [{"type": "text", "text": identity_message or "Tool not permitted."}]}
    preview = _preview_gate(
        tool_name="webhook_trigger",
        args=args,
        risk="high",
        summary=f"{method} {url}",
        signature_payload={"method": method, "url": url, "payload": payload or {}, "headers": headers},
        enforce_default=_plan_preview_require_ack,
    )
    if preview:
        record_summary("webhook_trigger", "dry_run", start_time, effect="plan_preview", risk="high")
        _audit(
            "webhook_trigger",
            _identity_enriched_audit(
                {"result": "preview_required", "method": method, "host": parsed.hostname or ""},
                identity_context,
                [*identity_chain, "decision:preview_required"],
            ),
        )
        return {"content": [{"type": "text", "text": preview}]}
    if _webhook_auth_token and not any(key.lower() == "authorization" for key in headers):
        headers["Authorization"] = f"Bearer {_webhook_auth_token}"
    timeout_sec = _as_float(
        args.get("timeout_sec", _webhook_timeout_sec),
        _webhook_timeout_sec,
        minimum=0.1,
        maximum=30.0,
    )
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(timeout_sec, minimum=0.1, maximum=30.0))
    request_kwargs: dict[str, Any] = {"headers": headers or None}
    if method in {"POST", "PUT", "PATCH"}:
        request_kwargs["json"] = payload or {}
    with _recovery_operation(
        "webhook_trigger",
        operation=f"{method} {parsed.hostname or ''}",
        context={"method": method, "host": parsed.hostname or ""},
    ) as recovery:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **request_kwargs) as resp:
                    body = await resp.text()
                    if 200 <= resp.status < 300:
                        _integration_record_success("webhook")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary("webhook_trigger", "ok", start_time)
                        _audit(
                            "webhook_trigger",
                            _identity_enriched_audit(
                                {
                                    "result": "ok",
                                    "method": method,
                                    "host": parsed.hostname or "",
                                    "status": resp.status,
                                    "response_length": len(body),
                                },
                                identity_context,
                                [*identity_chain, "decision:execute"],
                            ),
                        )
                        body_preview = body[:200]
                        suffix = f" body={body_preview}" if body_preview else ""
                        return {"content": [{"type": "text", "text": f"Webhook delivered ({resp.status}).{suffix}"}]}
                    if resp.status in {401, 403}:
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("webhook_trigger", start_time, "auth")
                        _dead_letter_enqueue(
                            "webhook_trigger",
                            args,
                            reason="auth",
                            detail=f"http_status={resp.status}",
                        )
                        _audit(
                            "webhook_trigger",
                            {"result": "auth", "method": method, "host": parsed.hostname or "", "status": resp.status},
                        )
                        return {"content": [{"type": "text", "text": "Webhook authentication failed."}]}
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("webhook_trigger", start_time, "http_error")
                    _dead_letter_enqueue(
                        "webhook_trigger",
                        args,
                        reason="http_error",
                        detail=f"http_status={resp.status}",
                    )
                    _audit(
                        "webhook_trigger",
                        {"result": "http_error", "method": method, "host": parsed.hostname or "", "status": resp.status},
                    )
                    return {"content": [{"type": "text", "text": f"Webhook request failed ({resp.status})."}]}
        except asyncio.TimeoutError:
            recovery.mark_failed("timeout")
            _record_service_error("webhook_trigger", start_time, "timeout")
            _dead_letter_enqueue("webhook_trigger", args, reason="timeout", detail="request timed out")
            _audit("webhook_trigger", {"result": "timeout", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Webhook request timed out."}]}
        except asyncio.CancelledError:
            recovery.mark_cancelled()
            _record_service_error("webhook_trigger", start_time, "cancelled")
            _dead_letter_enqueue("webhook_trigger", args, reason="cancelled", detail="request cancelled")
            _audit("webhook_trigger", {"result": "cancelled", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Webhook request was cancelled."}]}
        except aiohttp.ClientError:
            recovery.mark_failed("network_client_error")
            _record_service_error("webhook_trigger", start_time, "network_client_error")
            _dead_letter_enqueue("webhook_trigger", args, reason="network_client_error", detail="client transport failure")
            _audit("webhook_trigger", {"result": "network_client_error", "method": method, "host": parsed.hostname or ""})
            return {"content": [{"type": "text", "text": "Failed to reach webhook endpoint."}]}
        except Exception:
            recovery.mark_failed("unexpected")
            _record_service_error("webhook_trigger", start_time, "unexpected")
            _dead_letter_enqueue("webhook_trigger", args, reason="unexpected", detail="unexpected exception")
            _audit("webhook_trigger", {"result": "unexpected", "method": method, "host": parsed.hostname or ""})
            log.exception("Unexpected webhook_trigger failure")
            return {"content": [{"type": "text", "text": "Unexpected webhook trigger error."}]}


async def _calendar_fetch_events(
    *,
    calendar_entity_id: str | None,
    start_ts: float,
    end_ts: float,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    s = _services()
    _timestamp_to_iso_utc = s._timestamp_to_iso_utc
    _ha_get_json = s._ha_get_json
    _parse_calendar_event_timestamp = s._parse_calendar_event_timestamp

    params = {"start": _timestamp_to_iso_utc(start_ts), "end": _timestamp_to_iso_utc(end_ts)}
    entity_ids: list[str]
    if calendar_entity_id:
        entity_ids = [calendar_entity_id]
    else:
        calendars_payload, calendars_error = await _ha_get_json("/api/calendars")
        if calendars_error is not None:
            return None, calendars_error
        if not isinstance(calendars_payload, list):
            return None, "invalid_json"
        entity_ids = []
        for item in calendars_payload:
            if not isinstance(item, dict):
                continue
            entity = str(item.get("entity_id", "")).strip().lower()
            if entity:
                entity_ids.append(entity)
        if not entity_ids:
            return [], None
    events: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        payload, error_code = await _ha_get_json(f"/api/calendars/{entity_id}", params=params)
        if error_code is not None:
            return None, error_code
        if not isinstance(payload, list):
            return None, "invalid_json"
        for item in payload:
            if not isinstance(item, dict):
                continue
            start_raw = item.get("start")
            start_event = _parse_calendar_event_timestamp(start_raw)
            if start_event is None:
                continue
            end_event = _parse_calendar_event_timestamp(item.get("end"))
            all_day = isinstance(start_raw, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_raw.strip()))
            events.append(
                {
                    "entity_id": entity_id,
                    "summary": str(item.get("summary", "")).strip() or "(untitled)",
                    "location": str(item.get("location", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                    "start": start_raw,
                    "end": item.get("end"),
                    "start_ts": start_event,
                    "end_ts": end_event,
                    "all_day": all_day,
                }
            )
    events.sort(key=lambda event: float(event.get("start_ts", start_ts)))
    return events, None


def _parse_calendar_window(args: dict[str, Any]) -> tuple[float | None, float | None]:
    s = _services()
    time = s.time
    _parse_due_timestamp = s._parse_due_timestamp
    _as_float = s._as_float
    CALENDAR_DEFAULT_WINDOW_HOURS = s.CALENDAR_DEFAULT_WINDOW_HOURS
    CALENDAR_MAX_WINDOW_HOURS = s.CALENDAR_MAX_WINDOW_HOURS

    now = time.time()
    return _runtime_parse_calendar_window(
        args,
        now_ts=now,
        parse_due_timestamp=lambda value: _parse_due_timestamp(value, now_ts=now),
        as_float=lambda value, default: _as_float(
            value,
            default,
            minimum=0.1,
            maximum=CALENDAR_MAX_WINDOW_HOURS,
        ),
        default_window_hours=CALENDAR_DEFAULT_WINDOW_HOURS,
        max_window_hours=CALENDAR_MAX_WINDOW_HOURS,
    )


async def calendar_events(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _calendar_fetch_events = s._calendar_fetch_events

    start_time = time.monotonic()
    if not _tool_permitted("calendar_events"):
        record_summary("calendar_events", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("calendar_events", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    start_ts, end_ts = _parse_calendar_window(args)
    if start_ts is None or end_ts is None:
        _record_service_error("calendar_events", start_time, "invalid_data")
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid calendar window. Use valid ISO timestamps or relative durations for start/end.",
                }
            ]
        }
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=100)
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower() or None
    events, error_code = await _calendar_fetch_events(
        calendar_entity_id=calendar_entity_id,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    if error_code is not None:
        _record_service_error("calendar_events", start_time, error_code)
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Calendar endpoint or entity not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Calendar request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Calendar request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant calendar endpoint."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant calendar response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant calendar error."}]}
    rows = (events or [])[:limit]
    if not rows:
        record_summary("calendar_events", "empty", start_time)
        return {"content": [{"type": "text", "text": "No calendar events found in the selected window."}]}
    lines: list[str] = []
    for event in rows:
        start_value = float(event.get("start_ts", start_ts))
        if bool(event.get("all_day")):
            when = time.strftime("%Y-%m-%d", time.localtime(start_value)) + " (all day)"
        else:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_value))
        summary = str(event.get("summary", "(untitled)"))
        entity = str(event.get("entity_id", "calendar"))
        location = str(event.get("location", "")).strip()
        location_text = f" @ {location}" if location else ""
        lines.append(f"- {when} | {summary} [{entity}]{location_text}")
    record_summary("calendar_events", "ok", start_time)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def calendar_next_event(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _config = s._config
    _record_service_error = s._record_service_error
    _as_float = s._as_float
    _calendar_fetch_events = s._calendar_fetch_events
    CALENDAR_DEFAULT_WINDOW_HOURS = s.CALENDAR_DEFAULT_WINDOW_HOURS
    CALENDAR_MAX_WINDOW_HOURS = s.CALENDAR_MAX_WINDOW_HOURS

    start_time = time.monotonic()
    if not _tool_permitted("calendar_next_event"):
        record_summary("calendar_next_event", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _config or not _config.has_home_assistant:
        _record_service_error("calendar_next_event", start_time, "missing_config")
        return {"content": [{"type": "text", "text": "Home Assistant not configured. Set HASS_URL and HASS_TOKEN in .env."}]}
    window_hours = _as_float(
        args.get("window_hours", CALENDAR_DEFAULT_WINDOW_HOURS),
        CALENDAR_DEFAULT_WINDOW_HOURS,
        minimum=0.1,
        maximum=CALENDAR_MAX_WINDOW_HOURS,
    )
    now = time.time()
    calendar_entity_id = str(args.get("calendar_entity_id", "")).strip().lower() or None
    events, error_code = await _calendar_fetch_events(
        calendar_entity_id=calendar_entity_id,
        start_ts=now,
        end_ts=now + (window_hours * 3600.0),
    )
    if error_code is not None:
        _record_service_error("calendar_next_event", start_time, error_code)
        if error_code == "auth":
            return {"content": [{"type": "text", "text": "Home Assistant authentication failed. Check HASS_TOKEN."}]}
        if error_code == "not_found":
            return {"content": [{"type": "text", "text": "Calendar endpoint or entity not found."}]}
        if error_code == "timeout":
            return {"content": [{"type": "text", "text": "Calendar request timed out."}]}
        if error_code == "cancelled":
            return {"content": [{"type": "text", "text": "Calendar request was cancelled."}]}
        if error_code == "circuit_open":
            return {"content": [{"type": "text", "text": "Home Assistant circuit breaker is open; retry shortly."}]}
        if error_code == "network_client_error":
            return {"content": [{"type": "text", "text": "Failed to reach Home Assistant calendar endpoint."}]}
        if error_code == "invalid_json":
            return {"content": [{"type": "text", "text": "Invalid Home Assistant calendar response."}]}
        return {"content": [{"type": "text", "text": "Unexpected Home Assistant calendar error."}]}
    if not events:
        record_summary("calendar_next_event", "empty", start_time)
        return {"content": [{"type": "text", "text": "No upcoming calendar events found."}]}
    event = events[0]
    start_value = float(event.get("start_ts", now))
    if bool(event.get("all_day")):
        when = time.strftime("%Y-%m-%d", time.localtime(start_value)) + " (all day)"
    else:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_value))
    summary = str(event.get("summary", "(untitled)"))
    entity = str(event.get("entity_id", "calendar"))
    location = str(event.get("location", "")).strip()
    location_text = f" at {location}" if location else ""
    record_summary("calendar_next_event", "ok", start_time)
    return {"content": [{"type": "text", "text": f"Next event: {summary} on {when}{location_text} [{entity}]."}]}


async def webhook_inbound_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _inbound_webhook_events = s._inbound_webhook_events
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_list"):
        record_summary("webhook_inbound_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    rows = list(reversed(_inbound_webhook_events))[:limit]
    record_summary("webhook_inbound_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(rows, default=str)}]}


async def webhook_inbound_clear(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _inbound_webhook_events = s._inbound_webhook_events
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("webhook_inbound_clear"):
        record_summary("webhook_inbound_clear", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    count = len(_inbound_webhook_events)
    _inbound_webhook_events.clear()
    record_summary("webhook_inbound_clear", "ok", start_time)
    _audit("webhook_inbound_clear", {"result": "ok", "cleared_count": count})
    return {"content": [{"type": "text", "text": f"Cleared inbound webhook events: {count}."}]}


async def dead_letter_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _as_int = s._as_int
    _record_service_error = s._record_service_error
    _dead_letter_queue_status = s._dead_letter_queue_status
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("dead_letter_list"):
        record_summary("dead_letter_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    limit = _as_int(args.get("limit", 20), 20, minimum=1, maximum=200)
    status_filter = str(args.get("status", "open")).strip().lower() or "open"
    if status_filter not in {"open", "all", "pending", "failed", "replayed"}:
        _record_service_error("dead_letter_list", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "status must be one of open, all, pending, failed, replayed."}]}
    payload = _dead_letter_queue_status(limit=limit, status_filter=status_filter)
    payload["status_filter"] = status_filter
    record_summary("dead_letter_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


async def dead_letter_replay(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error
    _as_int = s._as_int
    _read_dead_letter_entries = s._read_dead_letter_entries
    _dead_letter_matches = s._dead_letter_matches
    webhook_trigger = s.webhook_trigger
    slack_notify = s.slack_notify
    discord_notify = s.discord_notify
    email_send = s.email_send
    pushover_notify = s.pushover_notify
    _tool_response_text = s._tool_response_text
    _tool_response_success = s._tool_response_success
    _write_dead_letter_entries = s._write_dead_letter_entries
    time = s.time
    _audit = s._audit
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("dead_letter_replay"):
        record_summary("dead_letter_replay", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    status_filter = str(args.get("status", "open")).strip().lower() or "open"
    if status_filter not in {"open", "all", "pending", "failed", "replayed"}:
        _record_service_error("dead_letter_replay", start_time, "invalid_data")
        return {"content": [{"type": "text", "text": "status must be one of open, all, pending, failed, replayed."}]}
    entry_id = str(args.get("entry_id", "")).strip()
    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    entries = _read_dead_letter_entries()
    if not entries:
        record_summary("dead_letter_replay", "empty", start_time)
        return {"content": [{"type": "text", "text": "Dead-letter queue is empty."}]}

    replay_handlers: dict[str, Any] = {
        "webhook_trigger": webhook_trigger,
        "slack_notify": slack_notify,
        "discord_notify": discord_notify,
        "email_send": email_send,
        "pushover_notify": pushover_notify,
    }
    selected_indexes: list[int] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        item_entry_id = str(entry.get("entry_id", "")).strip()
        if entry_id and item_entry_id != entry_id:
            continue
        if not _dead_letter_matches(entry, status_filter=status_filter):
            continue
        tool_name = str(entry.get("tool", "")).strip().lower()
        if tool_name not in replay_handlers:
            continue
        selected_indexes.append(idx)
        if not entry_id and len(selected_indexes) >= limit:
            break
    if not selected_indexes:
        record_summary("dead_letter_replay", "empty", start_time)
        return {"content": [{"type": "text", "text": "No matching dead-letter entries to replay."}]}

    replayed_count = 0
    failed_count = 0
    results: list[dict[str, Any]] = []
    for idx in selected_indexes:
        entry = entries[idx]
        tool_name = str(entry.get("tool", "")).strip().lower()
        handler = replay_handlers.get(tool_name)
        if handler is None:
            continue
        payload_raw = entry.get("args")
        payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
        payload["_dead_letter_replay"] = True
        replay_text = ""
        success = False
        try:
            replay_result = await handler(payload)
            replay_text = _tool_response_text(replay_result)
            success = _tool_response_success(replay_text)
        except Exception as exc:
            replay_text = f"{exc.__class__.__name__}: {exc}"
            success = False
        attempts = 0
        try:
            attempts = int(entry.get("attempts", 0) or 0)
        except (TypeError, ValueError):
            attempts = 0
        entry["attempts"] = attempts + 1
        entry["last_attempt_at"] = time.time()
        entry["last_error"] = "" if success else replay_text[:300]
        entry["status"] = "replayed" if success else "failed"
        if success:
            replayed_count += 1
        else:
            failed_count += 1
        results.append(
            {
                "entry_id": str(entry.get("entry_id", "")),
                "tool": tool_name,
                "status": str(entry.get("status", "unknown")),
                "result": replay_text[:300],
            }
        )
    _write_dead_letter_entries(entries)
    if failed_count > 0 and replayed_count == 0:
        record_summary("dead_letter_replay", "error", start_time, "replay_failed")
    else:
        record_summary("dead_letter_replay", "ok", start_time)
    payload = {
        "requested_entry_id": entry_id,
        "attempted_count": len(selected_indexes),
        "replayed_count": replayed_count,
        "failed_count": failed_count,
        "results": results,
    }
    _audit(
        "dead_letter_replay",
        {
            "result": "ok" if failed_count == 0 else "partial",
            "attempted_count": len(selected_indexes),
            "replayed_count": replayed_count,
            "failed_count": failed_count,
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}
