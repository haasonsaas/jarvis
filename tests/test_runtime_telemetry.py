from __future__ import annotations

from types import SimpleNamespace

from jarvis.runtime_telemetry import refresh_tool_error_counters


def test_refresh_tool_error_counters_sets_service_storage_and_unknown_totals() -> None:
    runtime = SimpleNamespace(
        _telemetry={"service_errors": 0.0, "storage_errors": 0.0, "unknown_summary_details": 0.0},
        _telemetry_error_counts={},
    )

    refresh_tool_error_counters(
        runtime,
        list_summaries_fn=lambda limit=200: [
            {"status": "error", "detail": "timeout"},
            {"status": "error", "detail": "storage_error"},
            {"status": "error", "detail": "not_a_real_code"},
            {"status": "ok", "detail": "timeout"},
        ],
        tool_service_error_codes={"timeout", "unknown_error"},
        storage_error_details={"storage_error"},
        service_error_details={"timeout", "http_error"},
    )

    assert runtime._telemetry["service_errors"] == 1.0
    assert runtime._telemetry["storage_errors"] == 1.0
    assert runtime._telemetry["unknown_summary_details"] == 1.0
    assert runtime._telemetry_error_counts == {"timeout": 1.0}


def test_refresh_tool_error_counters_noop_when_summary_listing_fails() -> None:
    runtime = SimpleNamespace(
        _telemetry={"service_errors": 2.0, "storage_errors": 1.0, "unknown_summary_details": 3.0},
        _telemetry_error_counts={"timeout": 2.0},
    )

    def _raise(**_kwargs):
        raise RuntimeError("boom")

    refresh_tool_error_counters(
        runtime,
        list_summaries_fn=_raise,
        tool_service_error_codes={"timeout"},
        storage_error_details={"storage_error"},
        service_error_details={"timeout"},
    )

    assert runtime._telemetry["service_errors"] == 2.0
    assert runtime._telemetry["storage_errors"] == 1.0
    assert runtime._telemetry["unknown_summary_details"] == 3.0
    assert runtime._telemetry_error_counts == {"timeout": 2.0}
