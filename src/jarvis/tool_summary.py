from __future__ import annotations

import math
import time
import threading
from collections import deque
from dataclasses import dataclass, asdict


@dataclass
class ToolSummary:
    name: str
    status: str
    duration_ms: float
    detail: str | None
    effect: str | None
    risk: str | None
    timestamp: float


class ToolSummaryStore:
    def __init__(self, maxlen: int = 200) -> None:
        self._items: deque[ToolSummary] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, summary: ToolSummary) -> None:
        with self._lock:
            self._items.appendleft(summary)

    def list(self, limit: int | float | str = 10) -> list[dict[str, object]]:
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError, OverflowError):
            parsed_limit = 10
        if isinstance(limit, float) and not math.isfinite(limit):
            parsed_limit = 10
        parsed_limit = max(1, min(200, parsed_limit))
        with self._lock:
            snapshot = list(self._items)[:parsed_limit]
        items = []
        for item in snapshot:
            payload = asdict(item)
            duration = payload.get("duration_ms")
            if isinstance(duration, (int, float)) and not math.isfinite(float(duration)):
                payload["duration_ms"] = 0.0
            items.append(payload)
        return items


_store = ToolSummaryStore()


def record_summary(
    name: str,
    status: str,
    start_time: float,
    detail: str | None = None,
    effect: str | None = None,
    risk: str | None = None,
) -> None:
    duration_ms = (time.monotonic() - start_time) * 1000.0
    if not math.isfinite(duration_ms) or duration_ms < 0.0:
        duration_ms = 0.0
    _store.add(ToolSummary(
        name=name,
        status=status,
        duration_ms=duration_ms,
        detail=detail,
        effect=effect,
        risk=risk,
        timestamp=time.time(),
    ))


def list_summaries(limit: int = 10) -> list[dict[str, object]]:
    return _store.list(limit)
