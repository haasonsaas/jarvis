#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

VALID_PROFILES = ("quick", "network", "storage", "contract")


def _normalize_profiles(raw: str) -> list[str]:
    items = [item.strip().lower() for item in (raw or "").split(",") if item.strip()]
    if not items:
        return list(VALID_PROFILES)
    invalid = [item for item in items if item not in VALID_PROFILES]
    if invalid:
        raise ValueError(
            f"invalid profile(s): {', '.join(invalid)}; expected {', '.join(VALID_PROFILES)}"
        )
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _permuted_orders(profiles: list[str], *, permutations: int) -> list[list[str]]:
    if permutations <= 0:
        raise ValueError("permutations must be >= 1")
    if not profiles:
        return []
    orders: list[list[str]] = []
    for idx in range(permutations):
        shift = idx % len(profiles)
        order = profiles[shift:] + profiles[:shift]
        if idx % 2 == 1:
            order = list(reversed(order))
        orders.append(order)
    return orders


def _phase_plan(*, orders: list[list[str]]) -> list[tuple[str, list[str]]]:
    phases: list[tuple[str, list[str]]] = []
    for permutation_index, order in enumerate(orders, start=1):
        for profile in order:
            phases.append(
                (
                    f"fault_{profile}_p{permutation_index}",
                    ["./scripts/run_fault_profiles.sh", profile],
                )
            )
        phases.append(
            (
                f"recovery_idempotence_p{permutation_index}",
                [
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                    "tests/test_tools_services.py",
                    "-k",
                    (
                        "dead_letter_queue_captures_webhook_failure_and_replays or "
                        "retry_backoff_delay_bounds_and_jitter or "
                        "bind_reconciles_interrupted_recovery_entries"
                    ),
                ],
            )
        )
    return phases


def _run_phase(name: str, command: list[str]) -> dict[str, object]:
    started_at = time.time()
    started_mono = time.monotonic()
    proc = subprocess.run(command, capture_output=True, text=True)
    finished_at = time.time()
    return {
        "phase": name,
        "command": command,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": time.monotonic() - started_mono,
        "exit_code": proc.returncode,
        "status": "passed" if proc.returncode == 0 else "failed",
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _artifact_checks(results: list[dict[str, object]], *, expected_phase_count: int) -> dict[str, object]:
    phase_names = [str(row.get("phase", "")) for row in results if str(row.get("phase", "")).strip()]
    valid_status = all(str(row.get("status", "")) in {"passed", "failed"} for row in results)
    has_timestamps = all(
        isinstance(row.get("started_at"), float) and isinstance(row.get("finished_at"), float)
        for row in results
    )
    return {
        "phase_names": phase_names,
        "all_status_valid": valid_status,
        "all_timestamps_present": has_timestamps,
        "expected_phase_count": expected_phase_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fault chaos permutations and recovery idempotence checks.")
    parser.add_argument(
        "--profiles",
        default="quick,network,storage,contract",
        help="Comma-separated fault profiles to permute.",
    )
    parser.add_argument(
        "--permutations",
        type=int,
        default=2,
        help="Number of deterministic profile permutations to run.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output artifact path. Defaults to fault-chaos-<profiles>-p<permutations>.json",
    )
    args = parser.parse_args()

    try:
        profiles = _normalize_profiles(args.profiles)
        orders = _permuted_orders(profiles, permutations=args.permutations)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    profile_tag = "-".join(profiles)
    output = args.output or f".artifacts/quality/fault-chaos-{profile_tag}-p{args.permutations}.json"

    plan = _phase_plan(orders=orders)
    results: list[dict[str, object]] = []
    failed = False
    for phase_index, (name, command) in enumerate(plan, start=1):
        result = _run_phase(name, command)
        result["phase_index"] = phase_index
        results.append(result)
        print(f"[fault-chaos] {name}: {result['status']} ({result['duration_sec']:.2f}s)")
        if int(result["exit_code"]) != 0:
            failed = True
            break

    accepted = (not failed) and all(int(row.get("exit_code", 1)) == 0 for row in results)
    summary = {
        "profiles": profiles,
        "permutations": args.permutations,
        "phase_count": len(results),
        "expected_phase_count": len(plan),
        "passed_count": sum(1 for row in results if row.get("status") == "passed"),
        "failed_count": sum(1 for row in results if row.get("status") != "passed"),
        "accepted": accepted,
        "artifact_checks": _artifact_checks(results, expected_phase_count=len(plan)),
        "results": results,
        "generated_at": time.time(),
    }

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
