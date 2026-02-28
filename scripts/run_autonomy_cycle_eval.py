#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_STATUS = {
    "scheduled",
    "waiting_checkpoint",
    "completed",
    "needs_replan",
    "in_progress",
    "failed",
}


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _as_non_negative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _validate_cycle_payload(cycle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in (
        "due_count",
        "executed_count",
        "blocked_count",
        "progressed_step_count",
        "retry_scheduled_count",
        "verification_failure_count",
        "replan_count",
    ):
        if key not in cycle:
            continue
        if _as_non_negative_int(cycle.get(key)) is None:
            errors.append(f"invalid_cycle_{key}")
    return errors


def _validate_status_payload(status: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in (
        "autonomy_task_count",
        "needs_replan_count",
        "retry_pending_count",
        "backlog_step_count",
    ):
        if key not in status:
            continue
        if _as_non_negative_int(status.get(key)) is None:
            errors.append(f"invalid_status_{key}")

    failure_taxonomy = status.get("failure_taxonomy")
    if failure_taxonomy is not None:
        if not isinstance(failure_taxonomy, dict):
            errors.append("invalid_status_failure_taxonomy")
        else:
            for key, value in failure_taxonomy.items():
                reason_code = str(key).strip().lower()
                if not reason_code:
                    errors.append("invalid_status_failure_taxonomy_reason")
                    continue
                if _as_non_negative_int(value) is None:
                    errors.append("invalid_status_failure_taxonomy_value")
    return errors


def _compare_expected(
    *,
    label: str,
    actual: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            mismatches.append(
                f"{label}.{key}: expected={expected_value!r} actual={actual_value!r}"
            )
    return mismatches


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("id", "case"))
    actual_cycle = _as_mapping(case.get("actual_cycle"))
    actual_status = _as_mapping(case.get("actual_status"))
    expected_cycle = _as_mapping(case.get("expected_cycle"))
    expected_status = _as_mapping(case.get("expected_status"))

    validation_errors = _validate_cycle_payload(actual_cycle)
    validation_errors.extend(_validate_status_payload(actual_status))

    mismatches = _compare_expected(
        label="cycle",
        actual=actual_cycle,
        expected=expected_cycle,
    )
    mismatches.extend(
        _compare_expected(
            label="status",
            actual=actual_status,
            expected=expected_status,
        )
    )

    for status_key in ("min_replan_count", "max_replan_count"):
        if status_key not in case:
            continue
        threshold = _as_non_negative_int(case.get(status_key))
        actual_value = _as_non_negative_int(actual_cycle.get("replan_count"))
        if threshold is None:
            mismatches.append(f"{status_key}: invalid threshold")
            continue
        if actual_value is None:
            mismatches.append("cycle.replan_count missing/invalid")
            continue
        if status_key.startswith("min") and actual_value < threshold:
            mismatches.append(
                f"cycle.replan_count below min ({actual_value} < {threshold})"
            )
        if status_key.startswith("max") and actual_value > threshold:
            mismatches.append(
                f"cycle.replan_count above max ({actual_value} > {threshold})"
            )

    for status_key, actual_key in (
        ("min_retry_pending_count", "retry_pending_count"),
        ("min_needs_replan_count", "needs_replan_count"),
        ("min_backlog_step_count", "backlog_step_count"),
    ):
        if status_key not in case:
            continue
        threshold = _as_non_negative_int(case.get(status_key))
        actual_value = _as_non_negative_int(actual_status.get(actual_key))
        if threshold is None:
            mismatches.append(f"{status_key}: invalid threshold")
            continue
        if actual_value is None:
            mismatches.append(f"status.{actual_key} missing/invalid")
            continue
        if actual_value < threshold:
            mismatches.append(
                f"status.{actual_key} below min ({actual_value} < {threshold})"
            )

    if "required_statuses" in case:
        required_statuses = case.get("required_statuses")
        status_counts = _as_mapping(actual_status.get("status_counts"))
        if not isinstance(required_statuses, list):
            mismatches.append("required_statuses must be a list")
        else:
            for item in required_statuses:
                status_name = str(item).strip().lower()
                if status_name not in ALLOWED_STATUS:
                    mismatches.append(f"invalid required status: {status_name!r}")
                    continue
                count = _as_non_negative_int(status_counts.get(status_name))
                if count is None or count <= 0:
                    mismatches.append(f"required status missing: {status_name}")

    if "min_failure_taxonomy_total" in case:
        threshold = _as_non_negative_int(case.get("min_failure_taxonomy_total"))
        failure_taxonomy = _as_mapping(actual_status.get("failure_taxonomy"))
        total = 0
        for value in failure_taxonomy.values():
            parsed = _as_non_negative_int(value)
            if parsed is not None:
                total += parsed
        if threshold is None:
            mismatches.append("min_failure_taxonomy_total: invalid threshold")
        elif total < threshold:
            mismatches.append(
                f"status.failure_taxonomy total below min ({total} < {threshold})"
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
    parser = argparse.ArgumentParser(
        description="Run deterministic planner autonomy-cycle contract checks."
    )
    parser.add_argument("dataset", help="Path to autonomy cycle contract dataset JSON")
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
