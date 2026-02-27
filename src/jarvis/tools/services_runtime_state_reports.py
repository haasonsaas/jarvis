"""Quality-report runtime helpers for services."""

from __future__ import annotations

from typing import Any

def quality_reports_snapshot(services_module: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    s = services_module
    if not s._quality_reports:
        return []
    capped = s._as_int(limit, 10, minimum=1, maximum=50)
    return [dict(item) for item in s._quality_reports[-capped:]][::-1]


def append_quality_report(services_module: Any, report: dict[str, Any]) -> None:
    s = services_module
    s._quality_reports.append({str(key): value for key, value in report.items()})
    if len(s._quality_reports) > s.CACHED_QUALITY_REPORT_MAX:
        del s._quality_reports[: len(s._quality_reports) - s.CACHED_QUALITY_REPORT_MAX]
    s._persist_expansion_state()
