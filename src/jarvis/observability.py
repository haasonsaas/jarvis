from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Any


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0.0:
        return float(values[0])
    if q >= 1.0:
        return float(values[-1])
    idx = (len(values) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return float(values[lo] + ((values[hi] - values[lo]) * frac))


def _default_intent_metrics() -> dict[str, float]:
    return {
        "turn_count": 0.0,
        "answer_intent_count": 0.0,
        "action_intent_count": 0.0,
        "hybrid_intent_count": 0.0,
        "answer_sample_count": 0.0,
        "completion_sample_count": 0.0,
        "answer_quality_success_rate": 0.0,
        "completion_success_rate": 0.0,
        "correction_count": 0.0,
        "correction_frequency": 0.0,
    }


def _safe_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return parsed


class ObservabilityStore:
    """Persistent observability state and metric export."""

    def __init__(
        self,
        *,
        db_path: str,
        state_path: str,
        event_log_path: str,
        failure_burst_threshold: int = 5,
    ) -> None:
        self._db_path = db_path
        self._state_path = Path(state_path)
        self._event_log_path = Path(event_log_path)
        self._failure_burst_threshold = max(1, int(failure_burst_threshold))

        parent = Path(db_path).expanduser().parent
        parent.mkdir(parents=True, exist_ok=True)
        self._state_path.expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._event_log_path.expanduser().parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(Path(db_path).expanduser()), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

        self._started_at = 0.0
        self._restart_count = 0
        self._alerts: deque[dict[str, Any]] = deque(maxlen=100)
        self._alert_last_emitted: dict[str, float] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=500)
        self._last_state = "unknown"

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                turns REAL NOT NULL,
                stt_ms REAL NOT NULL,
                llm_ms REAL NOT NULL,
                tts_ms REAL NOT NULL,
                service_errors REAL NOT NULL,
                storage_errors REAL NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_snapshots(ts DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS state_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_state_events_ts ON state_events(ts DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tool_outcomes_ts ON tool_outcomes(ts DESC)")
        self._conn.commit()

    def start(self) -> None:
        now = time.time()
        state = self._load_runtime_state()
        self._restart_count = int(state.get("restart_count", 0)) + 1
        self._started_at = now
        self._save_runtime_state(last_start=now, last_stop=float(state.get("last_stop", 0.0)))
        self.record_event("runtime_start", {"restart_count": self._restart_count})

    def stop(self) -> None:
        now = time.time()
        self._save_runtime_state(last_start=self._started_at, last_stop=now)
        self.record_event("runtime_stop", {"uptime_sec": self.uptime_sec()})

    def close(self) -> None:
        self._conn.close()

    def _load_runtime_state(self) -> dict[str, Any]:
        path = self._state_path.expanduser()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _save_runtime_state(self, *, last_start: float, last_stop: float) -> None:
        payload = {
            "restart_count": self._restart_count,
            "last_start": float(last_start),
            "last_stop": float(last_stop),
        }
        self._state_path.expanduser().write_text(json.dumps(payload, indent=2))

    def uptime_sec(self) -> float:
        if self._started_at <= 0.0:
            return 0.0
        return max(0.0, time.time() - self._started_at)

    def record_snapshot(self, snapshot: dict[str, Any]) -> None:
        ts = time.time()
        turns = float(snapshot.get("turns", 0.0) or 0.0)
        stt_ms = float(snapshot.get("avg_stt_latency_ms", 0.0) or 0.0)
        llm_ms = float(snapshot.get("avg_llm_first_sentence_ms", 0.0) or 0.0)
        tts_ms = float(snapshot.get("avg_tts_first_audio_ms", 0.0) or 0.0)
        service_errors = float(snapshot.get("service_errors", 0.0) or 0.0)
        storage_errors = float(snapshot.get("storage_errors", 0.0) or 0.0)
        self._conn.execute(
            """
            INSERT INTO telemetry_snapshots(ts, turns, stt_ms, llm_ms, tts_ms, service_errors, storage_errors, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                turns,
                stt_ms,
                llm_ms,
                tts_ms,
                service_errors,
                storage_errors,
                json.dumps(snapshot, default=str),
            ),
        )
        self._conn.commit()

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        ts = time.time()
        clean_payload = {str(key): value for key, value in payload.items()}
        self._events.append({"timestamp": ts, "event_type": event_type, "payload": clean_payload})
        self._conn.execute(
            "INSERT INTO state_events(ts, event_type, payload) VALUES (?, ?, ?)",
            (ts, str(event_type), json.dumps(clean_payload, default=str)),
        )
        self._conn.commit()
        try:
            with self._event_log_path.expanduser().open("a") as handle:
                handle.write(
                    json.dumps({"timestamp": ts, "event_type": event_type, "payload": clean_payload}, default=str) + "\n"
                )
        except OSError:
            pass

    def record_state_transition(self, state: str, *, reason: str = "state_change") -> None:
        normalized = str(state)
        if normalized == self._last_state:
            return
        previous = self._last_state
        self._last_state = normalized
        self.record_event(
            "state_transition",
            {"from": previous, "to": normalized, "reason": reason},
        )

    def record_tool_summaries(self, summaries: list[dict[str, Any]]) -> None:
        ts = time.time()
        with self._conn:
            for item in summaries:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "tool"))
                status = str(item.get("status", "unknown"))
                detail = str(item.get("detail", ""))
                self._conn.execute(
                    "INSERT INTO tool_outcomes(ts, tool_name, status, detail) VALUES (?, ?, ?, ?)",
                    (ts, name, status, detail),
                )

    def recent_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        size = max(1, min(500, int(limit)))
        return list(self._events)[-size:]

    def latency_percentiles(self, *, window_sec: float = 3600.0) -> dict[str, dict[str, float]]:
        cutoff = time.time() - max(1.0, float(window_sec))
        rows = self._conn.cursor().execute(
            "SELECT stt_ms, llm_ms, tts_ms FROM telemetry_snapshots WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
        stt = sorted([float(row["stt_ms"]) for row in rows if math.isfinite(float(row["stt_ms"]))])
        llm = sorted([float(row["llm_ms"]) for row in rows if math.isfinite(float(row["llm_ms"]))])
        tts = sorted([float(row["tts_ms"]) for row in rows if math.isfinite(float(row["tts_ms"]))])

        def pack(values: list[float]) -> dict[str, float]:
            return {
                "p50": _percentile(values, 0.5),
                "p95": _percentile(values, 0.95),
                "p99": _percentile(values, 0.99),
            }

        return {
            "stt_ms": pack(stt),
            "llm_first_sentence_ms": pack(llm),
            "tts_first_audio_ms": pack(tts),
        }

    def tool_success_rates(self, *, window_sec: float = 900.0) -> dict[str, dict[str, float]]:
        cutoff = time.time() - max(1.0, float(window_sec))
        rows = self._conn.cursor().execute(
            "SELECT tool_name, status, COUNT(*) AS c FROM tool_outcomes WHERE ts >= ? GROUP BY tool_name, status",
            (cutoff,),
        ).fetchall()
        totals: dict[str, float] = {}
        successes: dict[str, float] = {}
        errors: dict[str, float] = {}
        for row in rows:
            tool = str(row["tool_name"])
            status = str(row["status"])
            count = float(row["c"])
            totals[tool] = totals.get(tool, 0.0) + count
            if status == "ok":
                successes[tool] = successes.get(tool, 0.0) + count
            if status == "error":
                errors[tool] = errors.get(tool, 0.0) + count
        rates: dict[str, dict[str, float]] = {}
        for tool, total in totals.items():
            ok = successes.get(tool, 0.0)
            err = errors.get(tool, 0.0)
            rates[tool] = {
                "success_rate": (ok / total) if total > 0 else 0.0,
                "error_rate": (err / total) if total > 0 else 0.0,
                "count": total,
            }
        return rates

    def _telemetry_payload_rows(self, *, window_sec: float) -> list[tuple[float, dict[str, Any]]]:
        cutoff = time.time() - max(1.0, float(window_sec))
        rows = self._conn.cursor().execute(
            "SELECT ts, payload FROM telemetry_snapshots WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
        payload_rows: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"]))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            payload_rows.append((float(row["ts"]), payload))
        return payload_rows

    @staticmethod
    def _token_usage_totals(payload: dict[str, Any]) -> tuple[float, float]:
        usage = payload.get("llm_token_usage")
        if not isinstance(usage, dict):
            return 0.0, 0.0
        return (
            max(0.0, _safe_float(usage.get("total_tokens_total"))),
            max(0.0, _safe_float(usage.get("cost_usd_total"))),
        )

    def budget_metrics(self, *, window_sec: float = 3600.0) -> dict[str, Any]:
        window = max(1.0, float(window_sec))
        payload_rows = self._telemetry_payload_rows(window_sec=window)
        sample_count = len(payload_rows)
        lat = self.latency_percentiles(window_sec=window)
        tokens_per_hour = 0.0
        cost_usd_per_hour = 0.0
        if sample_count >= 2:
            start_ts, start_payload = payload_rows[0]
            end_ts, end_payload = payload_rows[-1]
            duration_sec = max(1.0, end_ts - start_ts)
            start_tokens, start_cost = self._token_usage_totals(start_payload)
            end_tokens, end_cost = self._token_usage_totals(end_payload)
            delta_tokens = max(0.0, end_tokens - start_tokens)
            delta_cost = max(0.0, end_cost - start_cost)
            tokens_per_hour = delta_tokens * (3600.0 / duration_sec)
            cost_usd_per_hour = delta_cost * (3600.0 / duration_sec)
        return {
            "window_sec": window,
            "sample_count": sample_count,
            "latency_p95_ms": {
                "stt_ms": _safe_float(lat.get("stt_ms", {}).get("p95")),
                "llm_first_sentence_ms": _safe_float(lat.get("llm_first_sentence_ms", {}).get("p95")),
                "tts_first_audio_ms": _safe_float(lat.get("tts_first_audio_ms", {}).get("p95")),
            },
            "tokens_per_hour": max(0.0, tokens_per_hour),
            "cost_usd_per_hour": max(0.0, cost_usd_per_hour),
        }

    def _emit_alert(
        self,
        *,
        alert_key: str,
        alert: dict[str, Any],
        cooldown_sec: float,
    ) -> bool:
        now = time.time()
        cooldown = max(1.0, float(cooldown_sec))
        last = float(self._alert_last_emitted.get(alert_key, 0.0) or 0.0)
        if (now - last) < cooldown:
            return False
        payload = {str(key): value for key, value in alert.items()}
        payload["timestamp"] = now
        self._alert_last_emitted[alert_key] = now
        self._alerts.append(payload)
        return True

    def detect_budget_violations(
        self,
        *,
        latency_p95_budget_ms: float | None = None,
        tokens_budget_per_hour: float | None = None,
        cost_budget_usd_per_hour: float | None = None,
        window_sec: float = 3600.0,
        cooldown_sec: float = 300.0,
    ) -> list[dict[str, Any]]:
        metrics = self.budget_metrics(window_sec=window_sec)
        alerts: list[dict[str, Any]] = []
        latency_budget = max(0.0, _safe_float(latency_p95_budget_ms))
        if latency_budget > 0.0:
            llm_p95 = _safe_float(metrics.get("latency_p95_ms", {}).get("llm_first_sentence_ms"))
            if llm_p95 > latency_budget:
                alert = {
                    "type": "latency_budget_exceeded",
                    "window_sec": float(window_sec),
                    "metric": "llm_first_sentence_p95_ms",
                    "value": llm_p95,
                    "budget": latency_budget,
                }
                if self._emit_alert(alert_key="latency_budget_exceeded", alert=alert, cooldown_sec=cooldown_sec):
                    alerts.append(dict(self._alerts[-1]))
        tokens_budget = max(0.0, _safe_float(tokens_budget_per_hour))
        if tokens_budget > 0.0:
            tokens_per_hour = _safe_float(metrics.get("tokens_per_hour"))
            if tokens_per_hour > tokens_budget:
                alert = {
                    "type": "tokens_budget_exceeded",
                    "window_sec": float(window_sec),
                    "metric": "tokens_per_hour",
                    "value": tokens_per_hour,
                    "budget": tokens_budget,
                }
                if self._emit_alert(alert_key="tokens_budget_exceeded", alert=alert, cooldown_sec=cooldown_sec):
                    alerts.append(dict(self._alerts[-1]))
        cost_budget = max(0.0, _safe_float(cost_budget_usd_per_hour))
        if cost_budget > 0.0:
            cost_per_hour = _safe_float(metrics.get("cost_usd_per_hour"))
            if cost_per_hour > cost_budget:
                alert = {
                    "type": "cost_budget_exceeded",
                    "window_sec": float(window_sec),
                    "metric": "cost_usd_per_hour",
                    "value": cost_per_hour,
                    "budget": cost_budget,
                }
                if self._emit_alert(alert_key="cost_budget_exceeded", alert=alert, cooldown_sec=cooldown_sec):
                    alerts.append(dict(self._alerts[-1]))
        return alerts

    @staticmethod
    def _coerce_intent_metrics(payload: Any) -> dict[str, float]:
        defaults = _default_intent_metrics()
        if not isinstance(payload, dict):
            return defaults
        metrics = dict(defaults)
        for key in defaults:
            raw = payload.get(key, defaults[key])
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = defaults[key]
            if not math.isfinite(value):
                value = defaults[key]
            metrics[key] = value
        return metrics

    def intent_success_metrics(self, *, window_sec: float = 3600.0) -> dict[str, float]:
        cutoff = time.time() - max(1.0, float(window_sec))
        row = self._conn.cursor().execute(
            "SELECT payload FROM telemetry_snapshots WHERE ts >= ? ORDER BY ts DESC LIMIT 1",
            (cutoff,),
        ).fetchone()
        if row is None:
            row = self._conn.cursor().execute(
                "SELECT payload FROM telemetry_snapshots ORDER BY ts DESC LIMIT 1",
            ).fetchone()
        if row is None:
            return _default_intent_metrics()
        try:
            payload = json.loads(str(row["payload"]))
        except Exception:
            return _default_intent_metrics()
        return self._coerce_intent_metrics(payload.get("intent_metrics"))

    def detect_failure_burst(self, *, window_sec: float = 300.0) -> list[dict[str, Any]]:
        cutoff = time.time() - max(1.0, float(window_sec))
        row = self._conn.cursor().execute(
            "SELECT COUNT(*) AS c FROM tool_outcomes WHERE ts >= ? AND status = 'error'",
            (cutoff,),
        ).fetchone()
        count = int(row["c"]) if row is not None else 0
        alerts: list[dict[str, Any]] = []
        if count >= self._failure_burst_threshold:
            alert = {
                "type": "failure_burst",
                "window_sec": float(window_sec),
                "error_count": count,
                "threshold": self._failure_burst_threshold,
            }
            if self._emit_alert(
                alert_key="failure_burst",
                alert=alert,
                cooldown_sec=max(30.0, float(window_sec) / 2.0),
            ):
                alerts.append(dict(self._alerts[-1]))
        return alerts

    def active_alerts(self, *, limit: int = 20) -> list[dict[str, Any]]:
        size = max(1, min(100, int(limit)))
        return list(self._alerts)[-size:]

    def status_snapshot(self) -> dict[str, Any]:
        budget = self.budget_metrics(window_sec=3600.0)
        return {
            "enabled": True,
            "uptime_sec": self.uptime_sec(),
            "restart_count": self._restart_count,
            "latency_percentiles": self.latency_percentiles(window_sec=3600.0),
            "tool_rates": self.tool_success_rates(window_sec=900.0),
            "intent_metrics": self.intent_success_metrics(window_sec=3600.0),
            "alerts": self.active_alerts(limit=20),
            "budget_metrics": budget,
        }

    def prometheus_metrics(self) -> str:
        status = self.status_snapshot()
        lat = status["latency_percentiles"]
        budget = status.get("budget_metrics", {})
        intent = self._coerce_intent_metrics(status.get("intent_metrics"))
        lines = [
            "# HELP jarvis_uptime_seconds Uptime since process start",
            "# TYPE jarvis_uptime_seconds gauge",
            f"jarvis_uptime_seconds {status['uptime_sec']:.3f}",
            "# HELP jarvis_restart_count Number of process starts tracked by observability state",
            "# TYPE jarvis_restart_count counter",
            f"jarvis_restart_count {status['restart_count']}",
        ]
        for metric_name, points in [
            ("jarvis_stt_latency_ms", lat.get("stt_ms", {})),
            ("jarvis_llm_first_sentence_latency_ms", lat.get("llm_first_sentence_ms", {})),
            ("jarvis_tts_first_audio_latency_ms", lat.get("tts_first_audio_ms", {})),
        ]:
            for quantile in ("p50", "p95", "p99"):
                value = float(points.get(quantile, 0.0) or 0.0)
                lines.append(f'{metric_name}{{quantile="{quantile}"}} {value:.3f}')
        for tool_name, payload in status.get("tool_rates", {}).items():
            safe_tool = tool_name.replace('"', "")
            lines.append(
                f'jarvis_tool_success_rate{{tool="{safe_tool}"}} {float(payload.get("success_rate", 0.0)):.6f}'
            )
            lines.append(
                f'jarvis_tool_error_rate{{tool="{safe_tool}"}} {float(payload.get("error_rate", 0.0)):.6f}'
            )
        lines.extend(
            [
                "# HELP jarvis_intent_answer_quality_success_rate Intent-level answer quality success proxy",
                "# TYPE jarvis_intent_answer_quality_success_rate gauge",
                f"jarvis_intent_answer_quality_success_rate {intent['answer_quality_success_rate']:.6f}",
                "# HELP jarvis_intent_completion_success_rate Intent-level completion success rate",
                "# TYPE jarvis_intent_completion_success_rate gauge",
                f"jarvis_intent_completion_success_rate {intent['completion_success_rate']:.6f}",
                "# HELP jarvis_intent_correction_frequency User correction frequency",
                "# TYPE jarvis_intent_correction_frequency gauge",
                f"jarvis_intent_correction_frequency {intent['correction_frequency']:.6f}",
                "# HELP jarvis_budget_tokens_per_hour Estimated LLM token usage rate over the observability window",
                "# TYPE jarvis_budget_tokens_per_hour gauge",
                f"jarvis_budget_tokens_per_hour {float(budget.get('tokens_per_hour', 0.0) or 0.0):.6f}",
                "# HELP jarvis_budget_cost_usd_per_hour Estimated LLM cost rate over the observability window",
                "# TYPE jarvis_budget_cost_usd_per_hour gauge",
                f"jarvis_budget_cost_usd_per_hour {float(budget.get('cost_usd_per_hour', 0.0) or 0.0):.6f}",
            ]
        )
        return "\n".join(lines) + "\n"
