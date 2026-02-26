from __future__ import annotations

from jarvis.observability import ObservabilityStore


def test_observability_store_persists_and_reports_percentiles(tmp_path):
    store = ObservabilityStore(
        db_path=str(tmp_path / "telemetry.sqlite"),
        state_path=str(tmp_path / "state.json"),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    store.start()
    try:
        for value in [100.0, 200.0, 300.0, 400.0, 500.0]:
            store.record_snapshot(
                {
                    "turns": 1,
                    "avg_stt_latency_ms": value,
                    "avg_llm_first_sentence_ms": value * 2,
                    "avg_tts_first_audio_ms": value * 3,
                    "service_errors": 0,
                    "storage_errors": 0,
                }
            )
        p = store.latency_percentiles(window_sec=3600)
        assert p["stt_ms"]["p50"] >= 200.0
        assert p["stt_ms"]["p95"] >= p["stt_ms"]["p50"]

        status = store.status_snapshot()
        assert status["enabled"] is True
        assert status["restart_count"] >= 1
    finally:
        store.stop()
        store.close()


def test_observability_failure_burst_detection(tmp_path):
    store = ObservabilityStore(
        db_path=str(tmp_path / "telemetry.sqlite"),
        state_path=str(tmp_path / "state.json"),
        event_log_path=str(tmp_path / "events.jsonl"),
        failure_burst_threshold=2,
    )
    store.start()
    try:
        store.record_tool_summaries(
            [
                {"name": "x", "status": "error", "detail": "timeout"},
                {"name": "y", "status": "error", "detail": "auth"},
            ]
        )
        alerts = store.detect_failure_burst(window_sec=3600)
        assert alerts
        assert alerts[0]["type"] == "failure_burst"
    finally:
        store.stop()
        store.close()


def test_observability_prometheus_metrics_contains_expected_lines(tmp_path):
    store = ObservabilityStore(
        db_path=str(tmp_path / "telemetry.sqlite"),
        state_path=str(tmp_path / "state.json"),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    store.start()
    try:
        store.record_snapshot(
            {
                "turns": 3,
                "avg_stt_latency_ms": 120.0,
                "avg_llm_first_sentence_ms": 230.0,
                "avg_tts_first_audio_ms": 340.0,
                "service_errors": 1,
                "storage_errors": 0,
            }
        )
        metrics = store.prometheus_metrics()
        assert "jarvis_uptime_seconds" in metrics
        assert "jarvis_restart_count" in metrics
        assert "jarvis_stt_latency_ms" in metrics
    finally:
        store.stop()
        store.close()
