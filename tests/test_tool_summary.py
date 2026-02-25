"""Tests for jarvis.tool_summary storage and limit parsing."""

import math
import time
from concurrent.futures import ThreadPoolExecutor

from jarvis.tool_summary import ToolSummaryStore, ToolSummary, record_summary, list_summaries


def _summary(name: str) -> ToolSummary:
    return ToolSummary(
        name=name,
        status="ok",
        duration_ms=12.0,
        detail=None,
        effect=None,
        risk=None,
        timestamp=time.time(),
    )


def test_list_limit_accepts_numeric_strings():
    store = ToolSummaryStore()
    store.add(_summary("a"))
    store.add(_summary("b"))
    items = store.list("1")
    assert len(items) == 1
    assert items[0]["name"] == "b"


def test_list_limit_handles_non_finite_values():
    store = ToolSummaryStore()
    store.add(_summary("a"))
    items_nan = store.list(math.nan)
    items_inf = store.list(math.inf)
    assert len(items_nan) == 1
    assert len(items_inf) == 1


def test_record_summary_clamps_non_finite_start_time():
    record_summary("nan_case", "ok", math.nan)
    payload = list_summaries(1)[0]
    assert payload["name"] == "nan_case"
    assert payload["duration_ms"] == 0.0


def test_store_add_and_list_are_thread_safe():
    store = ToolSummaryStore(maxlen=500)

    def _add_item(idx: int) -> None:
        store.add(_summary(f"item_{idx}"))

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(_add_item, range(120)))

    items = store.list(200)
    assert len(items) == 120
