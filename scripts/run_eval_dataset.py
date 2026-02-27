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


def _evaluate_results(
    *,
    dataset_path: Path,
    results: list[dict[str, Any]],
    strict: bool,
    min_pass_rate: float | None,
    max_failed: int | None,
) -> dict[str, Any]:
    passed = sum(1 for row in results if bool(row.get("passed")))
    failed = len(results) - passed
    pass_rate = (passed / len(results)) if results else 0.0
    accepted = (failed == 0) if strict else (passed >= failed)

    failure_reasons: list[str] = []
    if strict and failed > 0:
        failure_reasons.append("strict_failed_cases")
    if not strict and passed < failed:
        failure_reasons.append("non_strict_majority_failed")
    if min_pass_rate is not None and pass_rate < min_pass_rate:
        accepted = False
        failure_reasons.append("pass_rate_below_threshold")
    if max_failed is not None and failed > max_failed:
        accepted = False
        failure_reasons.append("failed_count_above_threshold")

    return {
        "dataset": str(dataset_path),
        "strict": strict,
        "thresholds": {
            "min_pass_rate": min_pass_rate,
            "max_failed": max_failed,
        },
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "accepted": accepted,
        "failure_reasons": failure_reasons,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic evaluation dataset checks.")
    parser.add_argument("dataset", help="Path to dataset JSON")
    parser.add_argument("--output", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=None,
        help="Optional minimum pass-rate acceptance threshold in [0.0, 1.0].",
    )
    parser.add_argument(
        "--max-failed",
        type=int,
        default=None,
        help="Optional maximum failed-case acceptance threshold (>= 0).",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if args.min_pass_rate is not None and (args.min_pass_rate < 0.0 or args.min_pass_rate > 1.0):
        raise SystemExit("--min-pass-rate must be between 0.0 and 1.0.")
    if args.max_failed is not None and args.max_failed < 0:
        raise SystemExit("--max-failed must be >= 0.")

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not isinstance(cases, list):
        raise SystemExit("Dataset format error: expected top-level object with 'cases' list.")

    results = [_evaluate_case(case) for case in cases if isinstance(case, dict)]
    summary = _evaluate_results(
        dataset_path=dataset_path,
        results=results,
        strict=bool(args.strict),
        min_pass_rate=args.min_pass_rate,
        max_failed=args.max_failed,
    )

    text = json.dumps(summary, indent=2)
    print(text)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")

    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
