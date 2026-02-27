"""Weather integration handlers."""

from __future__ import annotations

from typing import Any


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
