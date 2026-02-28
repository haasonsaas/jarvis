# Observability Runbook

## Scope

Jarvis observability covers:
- persistent telemetry snapshots in `OBSERVABILITY_DB_PATH`
- runtime event stream in `OBSERVABILITY_EVENT_LOG_PATH`
- restart and uptime state in `OBSERVABILITY_STATE_PATH`
- Prometheus/OpenMetrics export at `GET /metrics` (operator server)
- SSE event feed at `GET /events` (operator server)

## Key Signals

- Latency percentiles: STT / LLM-first-sentence / TTS-first-audio (`p50`, `p95`, `p99`)
- Tool rolling rates: per-tool `success_rate` / `error_rate` windows
- Intent success signals: `answer_quality_success_rate`, `completion_success_rate`, `correction_frequency`
- Unified scorecard: `jarvis_scorecard` and `system_status.scorecard` (latency, reliability, initiative, trust)
- Failure burst alerts: generated when recent tool errors exceed `OBSERVABILITY_FAILURE_BURST_THRESHOLD`
- Budget alerts:
  - `latency_budget_exceeded` when LLM first-sentence p95 breaches `OBSERVABILITY_LATENCY_BUDGET_P95_MS`
  - `tokens_budget_exceeded` when estimated hourly tokens breach `OBSERVABILITY_TOKENS_BUDGET_PER_HOUR`
  - `cost_budget_exceeded` when estimated hourly spend breaches `OBSERVABILITY_COST_BUDGET_USD_PER_HOUR`
- Router canary disagreement analytics: `observability.router_canary_analytics` for canary coverage and shadow disagreement rate
- Process lifecycle: `runtime_start`, `runtime_stop`, `restart_count`, `uptime_sec`

## Triage Flow

1. Check current health snapshot:
   - query `system_status`
   - inspect `observability.alerts`
2. Inspect metrics endpoint:
   - `curl http://127.0.0.1:8765/metrics`
   - verify spikes in p95/p99 latency lines
3. Inspect event stream and timeline:
   - `curl http://127.0.0.1:8765/events`
   - filter for `watchdog_reset`, `stt_fallback`, `tts_fallback_text_only`, `failure_burst`, budget alert types
4. Correlate with tool history:
   - query `tool_summary` and `tool_summary_text`
5. Inspect canary disagreement panel:
   - open Operator Console and inspect `Router Canary`
   - review `recent_disagreements` to identify mismatched primary vs shadow route decisions

## Tuning

- Increase snapshot density:
  - lower `OBSERVABILITY_SNAPSHOT_INTERVAL_SEC`
- Reduce noisy alerts:
  - raise `OBSERVABILITY_FAILURE_BURST_THRESHOLD`
  - increase `OBSERVABILITY_ALERT_COOLDOWN_SEC`
- Tune budget sensitivity:
  - adjust `OBSERVABILITY_LATENCY_BUDGET_P95_MS`
  - adjust `OBSERVABILITY_TOKENS_BUDGET_PER_HOUR` and `OBSERVABILITY_COST_BUDGET_USD_PER_HOUR`
  - adjust `OBSERVABILITY_BUDGET_WINDOW_SEC` for shorter/longer smoothing windows
- Tighten degraded-mode detection:
  - combine lower burst threshold with watchdog timeouts (`WATCHDOG_*`)

## SLO Suggestions

- STT p95 < 1200ms
- LLM first sentence p95 < 1800ms
- TTS first audio p95 < 700ms
- Tool error rate < 5% for critical integrations

## Backup / Retention

- Observability DB and event log are local files; include them in host backup policy.
- If disk pressure increases, rotate/trim event log and archive DB snapshots out of band.

## Related Runbooks

- `campaign-execution-runbook.md`
- `integrations-degradation-runbook.md`
- `autonomy-checkpoint-runbook.md`
