"""Tests for release/readiness helper scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_eval_dataset_threshold_reasons():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("run_eval_dataset_script", project_root / "scripts" / "run_eval_dataset.py")

    summary = module._evaluate_results(
        dataset_path=Path("dataset.json"),
        results=[{"id": "a", "passed": True}, {"id": "b", "passed": False}, {"id": "c", "passed": True}],
        strict=False,
        min_pass_rate=0.9,
        max_failed=0,
    )
    assert summary["accepted"] is False
    assert "pass_rate_below_threshold" in summary["failure_reasons"]
    assert "failed_count_above_threshold" in summary["failure_reasons"]

    strict_summary = module._evaluate_results(
        dataset_path=Path("dataset.json"),
        results=[{"id": "a", "passed": True}, {"id": "b", "passed": False}],
        strict=True,
        min_pass_rate=None,
        max_failed=None,
    )
    assert strict_summary["accepted"] is False
    assert "strict_failed_cases" in strict_summary["failure_reasons"]


def test_generate_quality_report_trend():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("generate_quality_report_script", project_root / "scripts" / "generate_quality_report.py")

    baseline = module._build_report(
        [
            {"action": "smart_home", "decision_outcome": "ok"},
            {"action": "smart_home", "decision_outcome": "error", "decision_reason": "timeout"},
        ]
    )
    report = module._build_report(
        [
            {"action": "smart_home", "decision_outcome": "ok"},
            {"action": "todoist_add_task", "decision_outcome": "denied", "decision_reason": "policy"},
            {"action": "todoist_add_task", "decision_outcome": "ok"},
        ],
        baseline=baseline,
        baseline_path="/tmp/baseline.json",
    )
    trend = report["trend"]
    assert trend["has_baseline"] is True
    assert trend["baseline_path"] == "/tmp/baseline.json"
    assert trend["total_events_delta"] == 1
    assert trend["failure_count_delta"] == 0
    assert isinstance(trend["failure_rate_delta"], float)


def test_run_soak_profile_live_has_extended_phases_and_artifact_checks():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("run_soak_profile_script", project_root / "scripts" / "run_soak_profile.py")

    live_phases = module._phase_commands("live")
    phase_names = [name for name, _ in live_phases]
    assert "sim_baseline" in phase_names
    assert "fault_network" in phase_names
    assert "operator_status_contract" in phase_names
    assert "eval_contract_strict" in phase_names

    checks = module._artifact_checks(
        [
            {
                "phase": "sim_baseline",
                "status": "passed",
                "started_at": 1.0,
                "finished_at": 2.0,
            }
        ]
    )
    assert checks["all_status_valid"] is True
    assert checks["all_timestamps_present"] is True
    assert checks["phase_names"] == ["sim_baseline"]
