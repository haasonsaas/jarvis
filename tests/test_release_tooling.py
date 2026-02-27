"""Tests for release/readiness helper scripts."""

from __future__ import annotations

import importlib.util
import json
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
        min_cases=None,
        duplicate_ids=[],
        missing_expected_tools_ids=[],
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
        min_cases=None,
        duplicate_ids=[],
        missing_expected_tools_ids=[],
    )
    assert strict_summary["accepted"] is False
    assert "strict_failed_cases" in strict_summary["failure_reasons"]

    contract_summary = module._evaluate_results(
        dataset_path=Path("dataset.json"),
        results=[{"id": "a", "passed": True}],
        strict=True,
        min_pass_rate=None,
        max_failed=None,
        min_cases=2,
        duplicate_ids=["a"],
        missing_expected_tools_ids=["a"],
    )
    assert contract_summary["accepted"] is False
    assert "insufficient_case_count" in contract_summary["failure_reasons"]
    assert "duplicate_case_ids" in contract_summary["failure_reasons"]
    assert "missing_expected_tools" in contract_summary["failure_reasons"]


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
                "cycle": 1,
            }
        ],
        expected_phase_count_per_cycle=2,
        repeat=3,
    )
    assert checks["all_status_valid"] is True
    assert checks["all_timestamps_present"] is True
    assert checks["phase_names"] == ["sim_baseline"]
    assert checks["expected_total_phase_count"] == 6
    assert checks["cycle_phase_counts"] == {"1": 1}


def test_run_sim_acceptance_profiles_and_artifact_checks():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("run_sim_acceptance_script", project_root / "scripts" / "run_sim_acceptance.py")

    fast_phases = [name for name, _ in module._phase_commands("fast")]
    full_phases = [name for name, _ in module._phase_commands("full")]
    assert "sim_stack_baseline" in fast_phases
    assert "voice_loop_edges" in fast_phases
    assert "autonomy_checkpoint_edges" in fast_phases
    assert "operator_contract_edges" not in fast_phases
    assert "operator_contract_edges" in full_phases
    assert "recovery_replay_edges" in full_phases

    checks = module._artifact_checks(
        [
            {
                "phase": "voice_loop_edges",
                "status": "passed",
                "started_at": 1.0,
                "finished_at": 2.0,
                "cycle": 1,
            }
        ],
        expected_phase_count_per_cycle=3,
        repeat=2,
    )
    assert checks["all_status_valid"] is True
    assert checks["all_timestamps_present"] is True
    assert checks["phase_names"] == ["voice_loop_edges"]
    assert checks["expected_total_phase_count"] == 6
    assert checks["cycle_phase_counts"] == {"1": 1}


def test_run_fault_campaign_profile_matrix_contract():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("run_fault_campaign_script", project_root / "scripts" / "run_fault_campaign.py")

    assert module._normalize_profiles("all") == ["quick", "network", "storage", "contract"]
    assert module._normalize_profiles("quick,network,quick") == ["quick", "network"]
    assert module._profile_tag(["quick", "network"]) == "quick-network"
    with pytest.raises(ValueError):
        module._normalize_profiles("quick,invalid")

    phases = module._phase_commands(["quick", "storage"])
    assert [name for name, _ in phases] == ["fault_quick", "fault_storage"]
    assert phases[0][1] == ["./scripts/run_fault_profiles.sh", "quick"]


def test_run_fault_chaos_permutations_and_plan_contract():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("run_fault_chaos_script", project_root / "scripts" / "run_fault_chaos.py")

    assert module._normalize_profiles("quick,network,quick") == ["quick", "network"]
    with pytest.raises(ValueError):
        module._normalize_profiles("quick,invalid")

    orders = module._permuted_orders(["quick", "network", "storage"], permutations=3)
    assert orders[0] == ["quick", "network", "storage"]
    assert orders[1] == ["quick", "storage", "network"]
    assert len(orders) == 3

    plan = module._phase_plan(orders=orders[:1])
    phase_names = [name for name, _ in plan]
    assert phase_names == [
        "fault_quick_p1",
        "fault_network_p1",
        "fault_storage_p1",
        "recovery_idempotence_p1",
    ]

    checks = module._artifact_checks(
        [
            {
                "phase": "fault_quick_p1",
                "status": "passed",
                "started_at": 1.0,
                "finished_at": 2.0,
            }
        ],
        expected_phase_count=4,
    )
    assert checks["all_status_valid"] is True
    assert checks["all_timestamps_present"] is True
    assert checks["expected_phase_count"] == 4


def test_check_quality_trends_builds_delta_checks():
    project_root = Path(__file__).resolve().parents[1]
    module = _load_script_module("check_quality_trends_script", project_root / "scripts" / "check_quality_trends.py")

    soak = {
        "failed_count": 0,
        "results": [
            {"phase": "sim_baseline", "duration_sec": 8.0},
            {"phase": "retry_and_circuit", "duration_sec": 2.0},
        ],
    }
    fault = {
        "failed_count": 0,
        "results": [
            {"phase": "fault_quick", "duration_sec": 1.5},
        ],
    }
    metrics = module._metric_snapshot(soak, fault)
    assert metrics["soak_failed_count"] == 0.0
    assert metrics["soak_sim_baseline_duration_sec"] == 8.0
    assert metrics["fault_quick_duration_sec"] == 1.5

    checks = module._build_checks(
        metrics=metrics,
        baseline={
            "soak": {
                "max_failed_count": 0,
                "baseline_avg_phase_duration_sec": 3.0,
                "max_avg_phase_duration_delta_sec": 2.0,
                "baseline_sim_baseline_duration_sec": 7.0,
                "max_sim_baseline_duration_delta_sec": 2.0,
            },
            "fault": {
                "max_failed_count": 0,
                "baseline_avg_phase_duration_sec": 1.0,
                "max_avg_phase_duration_delta_sec": 1.0,
                "baseline_quick_duration_sec": 1.0,
                "max_quick_duration_delta_sec": 1.0,
            },
        },
    )
    assert len(checks) == 6
    assert all("name" in check for check in checks)
    assert all("passed" in check for check in checks)


def test_assistant_contract_dataset_has_adversarial_coverage():
    project_root = Path(__file__).resolve().parents[1]
    dataset_path = project_root / "docs" / "evals" / "assistant-contract.json"
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    assert isinstance(cases, list)
    assert len(cases) >= 250

    case_ids = {str(case.get("id", "")) for case in cases if isinstance(case, dict)}
    required_ids = {
        "adv_prompt_injection_policy_override",
        "adv_identity_spoof_requester_mismatch",
        "adv_checkpoint_bypass_requires_token",
        "adv_circuit_breaker_short_circuit",
        "adv_plan_preview_token_ttl_enforced",
        "sim_voice_edge_001",
        "sim_autonomy_edge_001",
    }
    assert required_ids.issubset(case_ids)
