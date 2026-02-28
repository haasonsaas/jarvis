#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line_text = line.strip()
        if not line_text:
            continue
        try:
            row = json.loads(line_text)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _group_by_conversation(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        conversation_id = str(row.get("conversation_id", "default")).strip() or "default"
        grouped.setdefault(conversation_id, []).append(row)
    for conversation_id, bucket in grouped.items():
        grouped[conversation_id] = sorted(
            bucket,
            key=lambda row: float(row.get("timestamp", 0.0) or 0.0),
        )
    return grouped


def _trace_slice(rows: list[dict[str, Any]], *, max_turns: int) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for row in rows[:max_turns]:
        trace.append(
            {
                "turn_id": int(row.get("turn_id", 0) or 0),
                "parent_turn_id": row.get("parent_turn_id"),
                "intent": str(row.get("intent", "unknown")).strip().lower() or "unknown",
                "completion_success": row.get("completion_success"),
                "response_success": row.get("response_success"),
                "route_policy": (
                    dict(row.get("route_policy")) if isinstance(row.get("route_policy"), dict) else {}
                ),
                "interruption_route": (
                    dict(row.get("interruption_route"))
                    if isinstance(row.get("interruption_route"), dict)
                    else {}
                ),
            }
        )
    return trace


def synthesize_dataset(
    rows: list[dict[str, Any]],
    *,
    max_cases: int,
    max_turns_per_case: int,
) -> dict[str, Any]:
    grouped = _group_by_conversation(rows)
    cases: list[dict[str, Any]] = []
    for index, (conversation_id, bucket) in enumerate(grouped.items()):
        if index >= max_cases:
            break
        trace = _trace_slice(bucket, max_turns=max_turns_per_case)
        if not trace:
            continue
        cases.append(
            {
                "id": f"trace_autogen_{index + 1:03d}_{conversation_id}",
                "trace": trace,
                "min_total_score": 0.7,
                "min_response_success_rate": 0.7,
                "min_trace_linkage_rate": 0.8,
            }
        )
    return {"cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize trajectory eval dataset from conversation traces.")
    parser.add_argument("trace_input", help="Trace JSON or JSONL input path")
    parser.add_argument("--output", default="docs/evals/trajectory-trace-generated.json")
    parser.add_argument("--max-cases", type=int, default=200)
    parser.add_argument("--max-turns-per-case", type=int, default=12)
    args = parser.parse_args()

    trace_path = Path(args.trace_input)
    if not trace_path.exists():
        raise SystemExit(f"trace input not found: {trace_path}")
    rows = _load_rows(trace_path)
    dataset = synthesize_dataset(
        rows,
        max_cases=max(1, min(1000, int(args.max_cases))),
        max_turns_per_case=max(1, min(100, int(args.max_turns_per_case))),
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "trace_input": str(trace_path),
                "output": str(output_path),
                "row_count": len(rows),
                "case_count": len(dataset.get("cases", [])),
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
