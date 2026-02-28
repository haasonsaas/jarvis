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
                    "intent_metrics": {
                        "turn_count": 5.0,
                        "answer_quality_success_rate": 0.8,
                        "completion_success_rate": 0.7,
                        "correction_frequency": 0.1,
                    },
                }
            )
        p = store.latency_percentiles(window_sec=3600)
        assert p["stt_ms"]["p50"] >= 200.0
        assert p["stt_ms"]["p95"] >= p["stt_ms"]["p50"]

        status = store.status_snapshot()
        assert status["enabled"] is True
        assert status["restart_count"] >= 1
        assert "intent_metrics" in status
        assert status["intent_metrics"]["answer_quality_success_rate"] == 0.8
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
                "intent_metrics": {
                    "turn_count": 3.0,
                    "answer_quality_success_rate": 0.66,
                    "completion_success_rate": 0.5,
                    "correction_frequency": 0.33,
                },
            }
        )
        metrics = store.prometheus_metrics()
        assert "jarvis_uptime_seconds" in metrics
        assert "jarvis_restart_count" in metrics
        assert "jarvis_stt_latency_ms" in metrics
        assert "jarvis_intent_answer_quality_success_rate" in metrics
        assert "jarvis_intent_completion_success_rate" in metrics
        assert "jarvis_intent_correction_frequency" in metrics
        assert "jarvis_budget_tokens_per_hour" in metrics
        assert "jarvis_budget_cost_usd_per_hour" in metrics
    finally:
        store.stop()
        store.close()


def test_observability_budget_alerts_and_metrics(tmp_path):
    store = ObservabilityStore(
        db_path=str(tmp_path / "telemetry.sqlite"),
        state_path=str(tmp_path / "state.json"),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    store.start()
    try:
        store.record_snapshot(
            {
                "turns": 1,
                "avg_stt_latency_ms": 100.0,
                "avg_llm_first_sentence_ms": 4200.0,
                "avg_tts_first_audio_ms": 200.0,
                "service_errors": 0,
                "storage_errors": 0,
                "llm_token_usage": {
                    "prompt_tokens_total": 800.0,
                    "completion_tokens_total": 200.0,
                    "total_tokens_total": 1000.0,
                    "cost_usd_total": 0.1,
                },
            }
        )
        store.record_snapshot(
            {
                "turns": 2,
                "avg_stt_latency_ms": 120.0,
                "avg_llm_first_sentence_ms": 5100.0,
                "avg_tts_first_audio_ms": 250.0,
                "service_errors": 0,
                "storage_errors": 0,
                "llm_token_usage": {
                    "prompt_tokens_total": 2800.0,
                    "completion_tokens_total": 1800.0,
                    "total_tokens_total": 4600.0,
                    "cost_usd_total": 1.6,
                },
            }
        )

        budget = store.budget_metrics(window_sec=3600.0)
        assert budget["sample_count"] >= 2
        assert budget["latency_p95_ms"]["llm_first_sentence_ms"] >= 4200.0
        assert budget["tokens_per_hour"] > 0.0
        assert budget["cost_usd_per_hour"] > 0.0

        alerts = store.detect_budget_violations(
            latency_p95_budget_ms=2500.0,
            tokens_budget_per_hour=1000.0,
            cost_budget_usd_per_hour=0.5,
            window_sec=3600.0,
            cooldown_sec=3600.0,
        )
        alert_types = {row["type"] for row in alerts}
        assert "latency_budget_exceeded" in alert_types
        assert "tokens_budget_exceeded" in alert_types
        assert "cost_budget_exceeded" in alert_types

        # Cooldown suppresses duplicate emissions for the same breach.
        suppressed = store.detect_budget_violations(
            latency_p95_budget_ms=2500.0,
            tokens_budget_per_hour=1000.0,
            cost_budget_usd_per_hour=0.5,
            window_sec=3600.0,
            cooldown_sec=3600.0,
        )
        assert suppressed == []
    finally:
        store.stop()
        store.close()
