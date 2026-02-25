"""Tests for jarvis.tool_summary storage and limit parsing."""

import math
import time

from jarvis.tool_summary import ToolSummaryStore, ToolSummary


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

