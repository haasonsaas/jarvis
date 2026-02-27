#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Expected object JSON at {path}")


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def _phase_duration(summary: dict[str, Any], phase_name: str) -> float:
    for row in summary.get("results", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("phase", "")) != phase_name:
            continue
        try:
            return float(row.get("duration_sec", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _metric_snapshot(soak: dict[str, Any], fault: dict[str, Any]) -> dict[str, float]:
    soak_durations = [
        float(row.get("duration_sec", 0.0) or 0.0)
        for row in soak.get("results", [])
        if isinstance(row, dict)
    ]
    fault_durations = [
        float(row.get("duration_sec", 0.0) or 0.0)
        for row in fault.get("results", [])
        if isinstance(row, dict)
    ]
    return {
        "soak_failed_count": float(int(soak.get("failed_count", 0) or 0)),
        "soak_avg_phase_duration_sec": _mean(soak_durations),
        "soak_sim_baseline_duration_sec": _phase_duration(soak, "sim_baseline"),
        "fault_failed_count": float(int(fault.get("failed_count", 0) or 0)),
        "fault_avg_phase_duration_sec": _mean(fault_durations),
        "fault_quick_duration_sec": _phase_duration(fault, "fault_quick"),
    }


def _delta_check(*, name: str, actual: float, baseline: float, max_delta: float) -> dict[str, Any]:
    delta = actual - baseline
    limit = baseline + max_delta
    passed = delta <= max_delta
    return {
        "name": name,
        "actual": actual,
        "baseline": baseline,
        "delta": delta,
        "max_delta": max_delta,
        "limit": limit,
        "passed": passed,
    }


def _max_check(*, name: str, actual: float, max_allowed: float) -> dict[str, Any]:
    passed = actual <= max_allowed
    return {
        "name": name,
        "actual": actual,
        "max_allowed": max_allowed,
        "passed": passed,
    }


def _build_checks(
    *,
    metrics: dict[str, float],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    soak = baseline.get("soak", {}) if isinstance(baseline, dict) else {}
    fault = baseline.get("fault", {}) if isinstance(baseline, dict) else {}
    checks: list[dict[str, Any]] = [
        _max_check(
            name="soak_failed_count",
            actual=float(metrics.get("soak_failed_count", 0.0)),
            max_allowed=float(soak.get("max_failed_count", 0.0) or 0.0),
        ),
        _delta_check(
            name="soak_avg_phase_duration_sec",
            actual=float(metrics.get("soak_avg_phase_duration_sec", 0.0)),
            baseline=float(soak.get("baseline_avg_phase_duration_sec", 0.0) or 0.0),
            max_delta=float(soak.get("max_avg_phase_duration_delta_sec", 0.0) or 0.0),
        ),
        _delta_check(
            name="soak_sim_baseline_duration_sec",
            actual=float(metrics.get("soak_sim_baseline_duration_sec", 0.0)),
            baseline=float(soak.get("baseline_sim_baseline_duration_sec", 0.0) or 0.0),
            max_delta=float(soak.get("max_sim_baseline_duration_delta_sec", 0.0) or 0.0),
        ),
        _max_check(
            name="fault_failed_count",
            actual=float(metrics.get("fault_failed_count", 0.0)),
            max_allowed=float(fault.get("max_failed_count", 0.0) or 0.0),
        ),
        _delta_check(
            name="fault_avg_phase_duration_sec",
            actual=float(metrics.get("fault_avg_phase_duration_sec", 0.0)),
            baseline=float(fault.get("baseline_avg_phase_duration_sec", 0.0) or 0.0),
            max_delta=float(fault.get("max_avg_phase_duration_delta_sec", 0.0) or 0.0),
        ),
        _delta_check(
            name="fault_quick_duration_sec",
            actual=float(metrics.get("fault_quick_duration_sec", 0.0)),
            baseline=float(fault.get("baseline_quick_duration_sec", 0.0) or 0.0),
            max_delta=float(fault.get("max_quick_duration_delta_sec", 0.0) or 0.0),
        ),
    ]
    return checks


def _run_if_missing(path: Path, command: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality trend gate using soak/fault artifacts.")
    parser.add_argument(
        "--soak-artifact",
        default=".artifacts/quality/soak-profile-fast.json",
        help="Soak profile artifact JSON path",
    )
    parser.add_argument(
        "--fault-artifact",
        default=".artifacts/quality/fault-campaign-quick-repeat1.json",
        help="Fault campaign artifact JSON path",
    )
    parser.add_argument(
        "--baseline",
        default="config/quality-trend-baselines.json",
        help="Baseline thresholds JSON path",
    )
    parser.add_argument(
        "--output",
        default=".artifacts/quality/quality-trend-gate.json",
        help="Output summary JSON path",
    )
    parser.add_argument(
        "--no-build-missing",
        action="store_true",
        help="Do not auto-generate missing artifacts.",
    )
    args = parser.parse_args()

    soak_artifact = Path(args.soak_artifact)
    fault_artifact = Path(args.fault_artifact)
    baseline_path = Path(args.baseline)
    output_path = Path(args.output)

    if not args.no_build_missing:
        _run_if_missing(
            soak_artifact,
            [
                "./scripts/run_soak_profile.py",
                "--profile",
                "fast",
                "--repeat",
                "1",
                "--output",
                str(soak_artifact),
            ],
        )
        _run_if_missing(
            fault_artifact,
            [
                "./scripts/run_fault_campaign.py",
                "--profiles",
                "quick",
                "--repeat",
                "1",
                "--output",
                str(fault_artifact),
            ],
        )

    soak = _load_json(soak_artifact)
    fault = _load_json(fault_artifact)
    baseline = _load_json(baseline_path)

    metrics = _metric_snapshot(soak, fault)
    checks = _build_checks(metrics=metrics, baseline=baseline)
    accepted = all(bool(check.get("passed")) for check in checks)
    summary = {
        "accepted": accepted,
        "checks": checks,
        "metrics": metrics,
        "artifacts": {
            "soak_artifact": str(soak_artifact),
            "fault_artifact": str(fault_artifact),
            "baseline": str(baseline_path),
        },
        "generated_at": time.time(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
