"""Action handlers for quality_evaluator."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def quality_eval_weekly_report(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    suppress = s.suppress
    list_summaries = s.list_summaries
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response
    _write_quality_report_artifact = s._write_quality_report_artifact
    _append_quality_report = s._append_quality_report

    wins = _as_str_list(args.get("wins"))
    regressions = _as_str_list(args.get("regressions"))
    summaries: list[dict[str, Any]] = []
    with suppress(Exception):
        loaded = list_summaries(300)
        if isinstance(loaded, list):
            summaries = [dict(row) for row in loaded if isinstance(row, dict)]
    error_rows = [row for row in summaries if isinstance(row, dict) and str(row.get("status", "")).strip().lower() in {"error", "failed"}]
    success_rows = [row for row in summaries if isinstance(row, dict) and str(row.get("status", "")).strip().lower() in {"ok", "success"}]
    report = {
        "generated_at": time.time(),
        "errors": len(error_rows),
        "successes": len(success_rows),
        "wins": wins,
        "regressions": regressions,
        "top_failures": [str(row.get("name", "unknown")) for row in error_rows[:10]],
        "notes": "Weekly assistant quality report artifact.",
    }
    artifact_path = _write_quality_report_artifact(report, report_path=str(args.get("report_path", "")).strip() or None)
    report["artifact_path"] = artifact_path
    _append_quality_report(report)
    record_summary("quality_evaluator", "ok", start_time, effect="weekly_report", risk="low")
    return _expansion_payload_response({"action": "weekly_report", **report})


async def quality_eval_dataset_run(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_str_list = s._as_str_list
    _as_bool = s._as_bool
    _expansion_payload_response = s._expansion_payload_response

    dataset = args.get("dataset") if isinstance(args.get("dataset"), list) else []
    strict = _as_bool(args.get("strict"), default=False)
    passed = 0
    failed = 0
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(dataset):
        if not isinstance(row, dict):
            failed += 1
            rows.append({"index": idx, "status": "failed", "reason": "invalid_case"})
            continue
        name = str(row.get("name", f"case-{idx}")).strip() or f"case-{idx}"
        expected = _as_str_list(row.get("expected_contains"))
        actual = str(row.get("actual", "")).strip()
        ok = all(item in actual for item in expected) if expected else bool(actual)
        if ok:
            passed += 1
        else:
            failed += 1
        rows.append({"name": name, "status": "passed" if ok else "failed", "expected_contains": expected})
    payload = {
        "action": "dataset_run",
        "strict": strict,
        "case_count": len(dataset),
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / len(dataset)) if dataset else 0.0,
        "accepted": (failed == 0) if strict else (passed >= failed),
        "results": rows[:300],
    }
    record_summary("quality_evaluator", "ok", start_time, effect=f"dataset_passed={passed}", risk="low")
    return _expansion_payload_response(payload)


async def quality_eval_reports_list(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_int = s._as_int
    _quality_reports = s._quality_reports
    _quality_reports_snapshot = s._quality_reports_snapshot
    _expansion_payload_response = s._expansion_payload_response

    limit = _as_int(args.get("limit", 10), 10, minimum=1, maximum=50)
    payload = {"action": "reports_list", "count": len(_quality_reports), "reports": _quality_reports_snapshot(limit=limit)}
    record_summary("quality_evaluator", "ok", start_time, effect="reports_list", risk="low")
    return _expansion_payload_response(payload)
