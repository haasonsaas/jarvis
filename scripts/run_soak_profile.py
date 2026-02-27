#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def _phase_commands(profile: str) -> list[tuple[str, list[str]]]:
    phases: list[tuple[str, list[str]]] = [
        ("sim_baseline", ["./scripts/test_sim.sh"]),
        ("fault_quick", ["./scripts/run_fault_profiles.sh", "quick"]),
    ]
    if profile in {"full", "live"}:
        phases.extend(
            [
                ("fault_network", ["./scripts/run_fault_profiles.sh", "network"]),
                ("fault_storage", ["./scripts/run_fault_profiles.sh", "storage"]),
                ("fault_contract", ["./scripts/run_fault_profiles.sh", "contract"]),
            ]
        )
    phases.extend(
        [
            (
                "checkpoint_resume",
                [
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                    "tests/test_tools_services.py",
                    "-k",
                    "planner_engine_autonomy_cycle_requires_checkpoint_then_executes",
                ],
            ),
            (
                "retry_and_circuit",
                [
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                    "tests/test_tools_services.py",
                    "-k",
                    (
                        "retry_backoff_delay_bounds_and_jitter or "
                        "weather_circuit_breaker_blocks_requests_and_surfaces_status or "
                        "dead_letter_queue_captures_webhook_failure_and_replays"
                    ),
                ],
            ),
        ]
    )
    if profile == "live":
        phases.extend(
            [
                (
                    "release_channel_stable",
                    ["./scripts/check_release_channel.py", "--channel", "stable"],
                ),
                (
                    "operator_status_contract",
                    [
                        "uv",
                        "run",
                        "pytest",
                        "-q",
                        "tests/test_tools_services.py",
                        "-k",
                        "system_status_contract_reports_expected_fields or test_system_status_reports_snapshot",
                    ],
                ),
                (
                    "eval_contract_strict",
                    [
                        "./scripts/run_eval_dataset.py",
                        "docs/evals/assistant-contract.json",
                        "--strict",
                        "--min-pass-rate",
                        "1.0",
                        "--max-failed",
                        "0",
                    ],
                ),
            ]
        )
    return phases


def _run_phase(name: str, command: list[str]) -> dict[str, object]:
    started_at = time.time()
    started_mono = time.monotonic()
    proc = subprocess.run(command, capture_output=True, text=True)
    finished_at = time.time()
    duration_sec = time.monotonic() - started_mono
    return {
        "phase": name,
        "command": command,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "exit_code": proc.returncode,
        "status": "passed" if proc.returncode == 0 else "failed",
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _artifact_checks(
    results: list[dict[str, object]],
    *,
    expected_phase_count_per_cycle: int,
    repeat: int,
) -> dict[str, object]:
    names = [str(row.get("phase", "")) for row in results if str(row.get("phase", "")).strip()]
    valid_status = all(str(row.get("status", "")) in {"passed", "failed"} for row in results)
    has_timestamps = all(
        isinstance(row.get("started_at"), float) and isinstance(row.get("finished_at"), float)
        for row in results
    )
    cycle_phase_counts: dict[int, int] = {}
    for row in results:
        try:
            cycle = int(row.get("cycle", 1))
        except (TypeError, ValueError):
            cycle = 1
        cycle_phase_counts[cycle] = cycle_phase_counts.get(cycle, 0) + 1
    return {
        "phase_names": names,
        "all_status_valid": valid_status,
        "all_timestamps_present": has_timestamps,
        "expected_phase_count_per_cycle": expected_phase_count_per_cycle,
        "expected_total_phase_count": expected_phase_count_per_cycle * max(1, repeat),
        "cycle_phase_counts": {
            str(cycle): count for cycle, count in sorted(cycle_phase_counts.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phased Jarvis soak profile checks.")
    parser.add_argument("--profile", choices=("fast", "full", "live"), default="fast")
    parser.add_argument("--repeat", type=int, default=1, help="Run full phase set this many cycles.")
    parser.add_argument(
        "--output",
        default=".artifacts/quality/soak-profile.json",
        help="JSON artifact path",
    )
    args = parser.parse_args()
    if args.repeat <= 0:
        raise SystemExit("--repeat must be >= 1.")

    phase_plan = _phase_commands(args.profile)
    results: list[dict[str, object]] = []
    failed = False
    for cycle in range(1, args.repeat + 1):
        for phase_index, (name, command) in enumerate(phase_plan, start=1):
            result = _run_phase(name, command)
            result["cycle"] = cycle
            result["cycle_phase_index"] = phase_index
            results.append(result)
            print(
                f"[soak] cycle {cycle}/{args.repeat} {name}: "
                f"{result['status']} ({result['duration_sec']:.2f}s)"
            )
            if int(result["exit_code"]) != 0:
                failed = True
                break
        if failed:
            break

    phase_count_per_cycle = len(phase_plan)
    cycle_phase_counts: dict[int, int] = {}
    cycle_failed: dict[int, bool] = {}
    for row in results:
        cycle = int(row.get("cycle", 1) or 1)
        cycle_phase_counts[cycle] = cycle_phase_counts.get(cycle, 0) + 1
        if int(row.get("exit_code", 1)) != 0:
            cycle_failed[cycle] = True
    cycles_completed = sum(
        1
        for cycle in range(1, args.repeat + 1)
        if cycle_phase_counts.get(cycle, 0) == phase_count_per_cycle
        and not cycle_failed.get(cycle, False)
    )
    accepted = (
        cycles_completed == args.repeat
        and all(int(row.get("exit_code", 1)) == 0 for row in results)
    )

    summary = {
        "profile": args.profile,
        "repeat": args.repeat,
        "cycles_completed": cycles_completed,
        "phase_count": len(results),
        "passed_count": sum(1 for row in results if row.get("status") == "passed"),
        "failed_count": sum(1 for row in results if row.get("status") != "passed"),
        "accepted": accepted,
        "expected_phase_count": phase_count_per_cycle,
        "artifact_checks": _artifact_checks(
            results,
            expected_phase_count_per_cycle=phase_count_per_cycle,
            repeat=args.repeat,
        ),
        "results": results,
        "generated_at": time.time(),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if bool(summary["accepted"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
