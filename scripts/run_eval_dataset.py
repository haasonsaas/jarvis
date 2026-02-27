#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("id", "case"))
    actual_response = str(case.get("actual_response", ""))
    actual_tools = {str(item) for item in _as_list(case.get("actual_tools"))}
    expected_contains = _as_list(case.get("expected_contains"))
    expected_tools = {str(item) for item in _as_list(case.get("expected_tools"))}

    missing_text = [needle for needle in expected_contains if needle not in actual_response]
    missing_tools = sorted(expected_tools - actual_tools)
    passed = not missing_text and not missing_tools

    return {
        "id": case_id,
        "passed": passed,
        "missing_text": missing_text,
        "missing_tools": missing_tools,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic evaluation dataset checks.")
    parser.add_argument("dataset", help="Path to dataset JSON")
    parser.add_argument("--output", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not isinstance(cases, list):
        raise SystemExit("Dataset format error: expected top-level object with 'cases' list.")

    results = [_evaluate_case(case) for case in cases if isinstance(case, dict)]
    passed = sum(1 for row in results if row["passed"])
    failed = len(results) - passed
    summary = {
        "dataset": str(dataset_path),
        "strict": bool(args.strict),
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / len(results)) if results else 0.0,
        "accepted": (failed == 0) if args.strict else (passed >= failed),
        "results": results,
    }

    text = json.dumps(summary, indent=2)
    print(text)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")

    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
