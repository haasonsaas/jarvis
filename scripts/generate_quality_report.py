#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime
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


def _build_report(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(entries)
    by_action = Counter(str(row.get("action", "unknown")) for row in entries)
    by_outcome = Counter(str(row.get("decision_outcome", row.get("result", "unknown"))) for row in entries)
    failures = [row for row in entries if str(row.get("decision_outcome", row.get("result", ""))).lower() in {"failed", "denied", "blocked", "error"}]

    top_failure_reasons = Counter(str(row.get("decision_reason", row.get("reason", "unknown"))) for row in failures)

    return {
        "generated_at": time.time(),
        "total_events": total,
        "event_count_by_action": dict(by_action.most_common(20)),
        "event_count_by_outcome": dict(by_outcome),
        "failure_count": len(failures),
        "top_failure_reasons": dict(top_failure_reasons.most_common(10)),
        "wins": [
            "Maintained audit coverage for operational actions.",
            "Captured decision outcomes for trust/policy review.",
        ],
        "regressions": [
            "High failure counts should be triaged from top_failure_reasons.",
        ] if failures else [],
    }


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
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly Jarvis quality report artifacts.")
    parser.add_argument("--audit-log", default=str(Path.home() / ".jarvis" / "audit.jsonl"))
    parser.add_argument("--output-dir", default=str(Path(".artifacts") / "quality"))
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    audit_log = Path(args.audit_log).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = _read_jsonl(audit_log)
    report = _build_report(entries)

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
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
