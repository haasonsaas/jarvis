#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_STARTING_AGENT = {"conversation", "action", "safety"}
ALLOWED_FIRST_RESPONSE = {"answer", "act", "clarify", "acknowledge"}
ALLOWED_RESPONSE_MODE = {"brief", "normal", "deep"}
ALLOWED_CONFIDENCE_MODE = {"direct", "calibrated", "cautious"}
ALLOWED_PERSONA_POSTURE = {"social", "task", "safety"}
ALLOWED_RISK_LEVEL = {"low", "medium", "high", "critical"}


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _coerce_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence < 0.0 or confidence > 1.0:
        return None
    return confidence


def _route_validation_errors(route: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if "starting_agent" in route:
        starting_agent = str(route.get("starting_agent", "")).strip().lower()
        if starting_agent not in ALLOWED_STARTING_AGENT:
            errors.append("invalid_starting_agent")
    if "first_response_strategy" in route:
        strategy = str(route.get("first_response_strategy", "")).strip().lower()
        if strategy not in ALLOWED_FIRST_RESPONSE:
            errors.append("invalid_first_response_strategy")
    if "response_mode" in route:
        mode = str(route.get("response_mode", "")).strip().lower()
        if mode not in ALLOWED_RESPONSE_MODE:
            errors.append("invalid_response_mode")
    if "confidence_mode" in route:
        confidence_mode = str(route.get("confidence_mode", "")).strip().lower()
        if confidence_mode not in ALLOWED_CONFIDENCE_MODE:
            errors.append("invalid_confidence_mode")
    if "persona_posture" in route:
        posture = str(route.get("persona_posture", "")).strip().lower()
        if posture not in ALLOWED_PERSONA_POSTURE:
            errors.append("invalid_persona_posture")
    if "risk_level" in route:
        risk_level = str(route.get("risk_level", "")).strip().lower()
        if risk_level not in ALLOWED_RISK_LEVEL:
            errors.append("invalid_risk_level")
    if "requires_confirmation" in route and not isinstance(route.get("requires_confirmation"), bool):
        errors.append("invalid_requires_confirmation")
    if "route_confidence" in route and _coerce_confidence(route.get("route_confidence")) is None:
        errors.append("invalid_route_confidence")
    return errors


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("id", "case"))
    actual = _as_mapping(case.get("actual_route"))
    expected = _as_mapping(case.get("expected_route"))
    validation_errors = _route_validation_errors(actual)

    mismatches: list[str] = []
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            mismatches.append(f"{key}: expected={expected_value!r} actual={actual.get(key)!r}")

    min_confidence_raw = case.get("min_confidence")
    if min_confidence_raw is not None:
        min_confidence = _coerce_confidence(min_confidence_raw)
        actual_confidence = _coerce_confidence(actual.get("route_confidence"))
        if min_confidence is None:
            mismatches.append("invalid_min_confidence")
        elif actual_confidence is None or actual_confidence < min_confidence:
            mismatches.append(
                f"route_confidence below min ({actual_confidence!r} < {min_confidence!r})"
            )

    max_confidence_raw = case.get("max_confidence")
    if max_confidence_raw is not None:
        max_confidence = _coerce_confidence(max_confidence_raw)
        actual_confidence = _coerce_confidence(actual.get("route_confidence"))
        if max_confidence is None:
            mismatches.append("invalid_max_confidence")
        elif actual_confidence is None or actual_confidence > max_confidence:
            mismatches.append(
                f"route_confidence above max ({actual_confidence!r} > {max_confidence!r})"
            )

    passed = not validation_errors and not mismatches
    return {
        "id": case_id,
        "passed": passed,
        "validation_errors": validation_errors,
        "mismatches": mismatches,
    }


def _evaluate_results(
    *,
    dataset_path: Path,
    results: list[dict[str, Any]],
    strict: bool,
    min_pass_rate: float | None,
    max_failed: int | None,
    min_cases: int | None,
    duplicate_ids: list[str],
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
    if min_cases is not None and len(results) < min_cases:
        accepted = False
        failure_reasons.append("insufficient_case_count")
    if duplicate_ids:
        accepted = False
        failure_reasons.append("duplicate_case_ids")

    return {
        "dataset": str(dataset_path),
        "strict": strict,
        "thresholds": {
            "min_pass_rate": min_pass_rate,
            "max_failed": max_failed,
            "min_cases": min_cases,
        },
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "accepted": accepted,
        "failure_reasons": failure_reasons,
        "duplicate_ids": duplicate_ids,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic policy-router evaluation checks.")
    parser.add_argument("dataset", help="Path to router policy dataset JSON")
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
    parser.add_argument(
        "--min-cases",
        type=int,
        default=None,
        help="Optional minimum number of evaluation cases required.",
    )
    parser.add_argument(
        "--require-unique-ids",
        action="store_true",
        help="Fail if case IDs are duplicated.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if args.min_pass_rate is not None and (args.min_pass_rate < 0.0 or args.min_pass_rate > 1.0):
        raise SystemExit("--min-pass-rate must be between 0.0 and 1.0.")
    if args.max_failed is not None and args.max_failed < 0:
        raise SystemExit("--max-failed must be >= 0.")
    if args.min_cases is not None and args.min_cases < 0:
        raise SystemExit("--min-cases must be >= 0.")

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not isinstance(cases, list):
        raise SystemExit("Dataset format error: expected top-level object with 'cases' list.")

    case_rows = [case for case in cases if isinstance(case, dict)]
    results = [_evaluate_case(case) for case in case_rows]
    case_ids = [str(case.get("id", "")).strip() for case in case_rows]
    id_counts: dict[str, int] = {}
    for case_id in case_ids:
        if not case_id:
            continue
        id_counts[case_id] = id_counts.get(case_id, 0) + 1
    duplicate_ids = sorted(case_id for case_id, count in id_counts.items() if count > 1)
    if not args.require_unique_ids:
        duplicate_ids = []

    summary = _evaluate_results(
        dataset_path=dataset_path,
        results=results,
        strict=bool(args.strict),
        min_pass_rate=args.min_pass_rate,
        max_failed=args.max_failed,
        min_cases=args.min_cases,
        duplicate_ids=duplicate_ids,
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
