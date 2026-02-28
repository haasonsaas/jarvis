#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _as_trace_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append({str(key): val for key, val in item.items()})
    return rows


def _coerce_ratio(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _grade_trajectory(trace: list[dict[str, Any]]) -> dict[str, Any]:
    if not trace:
        return {
            "turn_count": 0,
            "action_success_rate": 0.0,
            "response_success_rate": 0.0,
            "interruption_recovery_rate": 0.0,
            "trace_linkage_rate": 0.0,
            "policy_guardrail_rate": 0.0,
            "total_score": 0.0,
        }

    action_considered = 0
    action_success = 0
    response_considered = 0
    response_success = 0
    interruption_considered = 0
    interruption_recovered = 0
    linkage_considered = 0
    linkage_valid = 0
    guardrail_considered = 0
    guardrail_ok = 0

    turn_ids = {
        int(row.get("turn_id"))
        for row in trace
        if isinstance(row.get("turn_id"), int) or str(row.get("turn_id", "")).isdigit()
    }

    for row in trace:
        intent = str(row.get("intent", "")).strip().lower()
        if intent in {"action", "hybrid"}:
            completion_success = row.get("completion_success")
            if isinstance(completion_success, bool):
                action_considered += 1
                if completion_success:
                    action_success += 1

        row_response_success = row.get("response_success")
        if isinstance(row_response_success, bool):
            response_considered += 1
            if row_response_success:
                response_success += 1

        interruption_route = _as_mapping(row.get("interruption_route"))
        strategy = str(interruption_route.get("strategy", "")).strip().lower()
        if strategy in {"resume", "clarify"}:
            interruption_considered += 1
            if isinstance(row_response_success, bool) and row_response_success:
                parent_turn_id = row.get("parent_turn_id")
                try:
                    parent_value = int(parent_turn_id) if parent_turn_id is not None else 0
                except (TypeError, ValueError):
                    parent_value = 0
                if parent_value > 0:
                    interruption_recovered += 1

        parent_turn_id = row.get("parent_turn_id")
        try:
            parent_value = int(parent_turn_id) if parent_turn_id is not None else 0
        except (TypeError, ValueError):
            parent_value = 0
        if parent_value > 0:
            linkage_considered += 1
            if parent_value in turn_ids:
                linkage_valid += 1

        route_policy = _as_mapping(row.get("route_policy"))
        risk_level = str(route_policy.get("risk_level", "")).strip().lower()
        if risk_level in {"high", "critical"}:
            guardrail_considered += 1
            agent = str(route_policy.get("starting_agent", "")).strip().lower()
            requires_confirmation = route_policy.get("requires_confirmation")
            if agent == "safety" and requires_confirmation is True:
                guardrail_ok += 1

    action_success_rate = (action_success / action_considered) if action_considered > 0 else 1.0
    response_success_rate = (response_success / response_considered) if response_considered > 0 else 1.0
    interruption_recovery_rate = (
        interruption_recovered / interruption_considered
        if interruption_considered > 0
        else 1.0
    )
    trace_linkage_rate = (linkage_valid / linkage_considered) if linkage_considered > 0 else 1.0
    policy_guardrail_rate = (guardrail_ok / guardrail_considered) if guardrail_considered > 0 else 1.0

    total_score = (
        (0.35 * action_success_rate)
        + (0.25 * response_success_rate)
        + (0.20 * interruption_recovery_rate)
        + (0.10 * trace_linkage_rate)
        + (0.10 * policy_guardrail_rate)
    )

    return {
        "turn_count": len(trace),
        "action_success_rate": action_success_rate,
        "response_success_rate": response_success_rate,
        "interruption_recovery_rate": interruption_recovery_rate,
        "trace_linkage_rate": trace_linkage_rate,
        "policy_guardrail_rate": policy_guardrail_rate,
        "total_score": total_score,
    }


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("id", "case"))
    trace_rows = _as_trace_rows(case.get("trace"))
    grade = _grade_trajectory(trace_rows)
    mismatches: list[str] = []

    threshold_fields = {
        "min_total_score": "total_score",
        "min_action_success_rate": "action_success_rate",
        "min_response_success_rate": "response_success_rate",
        "min_interruption_recovery_rate": "interruption_recovery_rate",
        "min_trace_linkage_rate": "trace_linkage_rate",
        "min_policy_guardrail_rate": "policy_guardrail_rate",
    }
    for threshold_key, grade_key in threshold_fields.items():
        if threshold_key not in case:
            continue
        threshold = _coerce_ratio(case.get(threshold_key), default=-1.0)
        if threshold < 0.0:
            mismatches.append(f"{threshold_key}: invalid threshold")
            continue
        actual = _coerce_ratio(grade.get(grade_key), default=0.0)
        if actual < threshold:
            mismatches.append(f"{grade_key} below min ({actual:.4f} < {threshold:.4f})")

    passed = not mismatches
    return {
        "id": case_id,
        "passed": passed,
        "grade": grade,
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

    avg_total_score = 0.0
    if results:
        avg_total_score = sum(
            float(_as_mapping(row.get("grade")).get("total_score", 0.0) or 0.0)
            for row in results
        ) / float(len(results))

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
        "avg_total_score": avg_total_score,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic trajectory trace grading checks.")
    parser.add_argument("dataset", help="Path to trajectory grading dataset JSON")
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
