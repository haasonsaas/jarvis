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
                "timestamp": time.time(),
                "type": "failure_burst",
                "window_sec": float(window_sec),
                "error_count": count,
                "threshold": self._failure_burst_threshold,
            }
            self._alerts.append(alert)
            alerts.append(alert)
        return alerts

    def active_alerts(self, *, limit: int = 20) -> list[dict[str, Any]]:
        size = max(1, min(100, int(limit)))
        return list(self._alerts)[-size:]

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "uptime_sec": self.uptime_sec(),
            "restart_count": self._restart_count,
            "latency_percentiles": self.latency_percentiles(window_sec=3600.0),
            "tool_rates": self.tool_success_rates(window_sec=900.0),
            "alerts": self.active_alerts(limit=20),
        }

    def prometheus_metrics(self) -> str:
        status = self.status_snapshot()
        lat = status["latency_percentiles"]
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
        return "\n".join(lines) + "\n"
