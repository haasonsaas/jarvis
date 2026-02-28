#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _failure_rate(*, total_events: int, failure_count: int) -> float:
    if total_events <= 0:
        return 0.0
    return float(failure_count) / float(total_events)


def _build_trend(
    *,
    report: dict[str, Any],
    baseline: dict[str, Any] | None,
    baseline_path: str = "",
) -> dict[str, Any]:
    if not isinstance(baseline, dict):
        return {
            "has_baseline": False,
            "baseline_path": "",
            "baseline_generated_at": 0.0,
            "total_events_delta": 0,
            "failure_count_delta": 0,
            "failure_rate_delta": 0.0,
        }

    current_total = int(report.get("total_events", 0) or 0)
    current_failures = int(report.get("failure_count", 0) or 0)
    baseline_total = int(baseline.get("total_events", 0) or 0)
    baseline_failures = int(baseline.get("failure_count", 0) or 0)
    current_failure_rate = _failure_rate(total_events=current_total, failure_count=current_failures)
    baseline_failure_rate = _failure_rate(total_events=baseline_total, failure_count=baseline_failures)
    return {
        "has_baseline": True,
        "baseline_path": baseline_path,
        "baseline_generated_at": float(baseline.get("generated_at", 0.0) or 0.0),
        "total_events_delta": current_total - baseline_total,
        "failure_count_delta": current_failures - baseline_failures,
        "failure_rate_delta": current_failure_rate - baseline_failure_rate,
    }


def _build_report(
    entries: list[dict[str, Any]],
    *,
    baseline: dict[str, Any] | None = None,
    baseline_path: str = "",
) -> dict[str, Any]:
    total = len(entries)
    by_action = Counter(str(row.get("action", "unknown")) for row in entries)
    by_outcome = Counter(str(row.get("decision_outcome", row.get("result", "unknown"))) for row in entries)
    failures = [row for row in entries if str(row.get("decision_outcome", row.get("result", ""))).lower() in {"failed", "denied", "blocked", "error"}]

    top_failure_reasons = Counter(str(row.get("decision_reason", row.get("reason", "unknown"))) for row in failures)

    report = {
        "generated_at": time.time(),
        "total_events": total,
        "event_count_by_action": dict(by_action.most_common(20)),
        "event_count_by_outcome": dict(by_outcome),
        "failure_count": len(failures),
        "failure_rate": _failure_rate(total_events=total, failure_count=len(failures)),
        "top_failure_reasons": dict(top_failure_reasons.most_common(10)),
        "wins": [
            "Maintained audit coverage for operational actions.",
            "Captured decision outcomes for trust/policy review.",
        ],
        "regressions": [
            "High failure counts should be triaged from top_failure_reasons.",
        ] if failures else [],
    }
    report["trend"] = _build_trend(report=report, baseline=baseline, baseline_path=baseline_path)
    return report


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _latest_report_path(output_dir: Path) -> Path | None:
    candidates = sorted(output_dir.glob("weekly-quality-*.json"))
    if not candidates:
        return None
    return candidates[-1]


def _markdown(report: dict[str, Any]) -> str:
    generated = datetime.fromtimestamp(float(report.get("generated_at", 0.0))).isoformat()
    lines = [
        "# Jarvis Weekly Quality Report",
        "",
        f"Generated: {generated}",
        "",
        f"- Total events: {int(report.get('total_events', 0))}",
        f"- Failure events: {int(report.get('failure_count', 0))}",
        "",
        "## Outcome Distribution",
    ]
    for key, value in sorted((report.get("event_count_by_outcome") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Top Failure Reasons")
    reasons = report.get("top_failure_reasons") or {}
    if isinstance(reasons, dict) and reasons:
        for key, value in reasons.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    trend = report.get("trend") if isinstance(report.get("trend"), dict) else {}
    lines.append("")
    lines.append("## Trend")
    if trend and bool(trend.get("has_baseline")):
        lines.append(f"- Baseline: {trend.get('baseline_path', '')}")
        lines.append(f"- Total events delta: {int(trend.get('total_events_delta', 0) or 0)}")
        lines.append(f"- Failure events delta: {int(trend.get('failure_count_delta', 0) or 0)}")
        lines.append(f"- Failure-rate delta: {float(trend.get('failure_rate_delta', 0.0) or 0.0):+.4f}")
    else:
        lines.append("- Baseline report unavailable; trend not computed.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly Jarvis quality report artifacts.")
    parser.add_argument("--audit-log", default=str(Path.home() / ".jarvis" / "audit.jsonl"))
    parser.add_argument("--output-dir", default=str(Path(".artifacts") / "quality"))
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--compare-with",
        default="",
        help="Optional baseline report path. If omitted, compares against latest report in --output-dir.",
    )
    args = parser.parse_args()

    audit_log = Path(args.audit_log).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = _read_jsonl(audit_log)
    if args.compare_with.strip():
        baseline_path = Path(args.compare_with).expanduser()
    else:
        baseline_path = _latest_report_path(output_dir) or Path("")
    baseline = _load_json(baseline_path) if str(baseline_path) else None
    report = _build_report(
        entries,
        baseline=baseline,
        baseline_path=str(baseline_path) if baseline is not None else "",
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"weekly-quality-{stamp}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    artifact: dict[str, Any] = {
        "json": str(json_path),
        "markdown": "",
    }
    if args.markdown:
        md_path = output_dir / f"weekly-quality-{stamp}.md"
        md_path.write_text(_markdown(report), encoding="utf-8")
        artifact["markdown"] = str(md_path)

    print(json.dumps({"report": report, "artifacts": artifact}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
