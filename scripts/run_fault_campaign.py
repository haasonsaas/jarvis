#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

VALID_PROFILES = ("quick", "network", "storage", "contract")


def _normalize_profiles(raw: str) -> list[str]:
    text = (raw or "").strip().lower()
    if text == "all":
        return list(VALID_PROFILES)
    items = [item.strip().lower() for item in text.split(",") if item.strip()]
    if not items:
        raise ValueError("--profiles must include at least one profile")
    invalid = [item for item in items if item not in VALID_PROFILES]
    if invalid:
        raise ValueError(
            f"invalid profile(s): {', '.join(invalid)}; expected {', '.join(VALID_PROFILES)}"
        )
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _profile_tag(profiles: list[str]) -> str:
    return "-".join(profiles)


def _phase_commands(profiles: list[str]) -> list[tuple[str, list[str]]]:
    return [
        (f"fault_{profile}", ["./scripts/run_fault_profiles.sh", profile])
        for profile in profiles
    ]


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable fault campaign profile matrix.")
    parser.add_argument(
        "--profiles",
        default="quick,network,storage,contract",
        help="Comma-separated profiles or 'all'.",
    )
    parser.add_argument("--repeat", type=int, default=2, help="Run profile set this many cycles.")
    parser.add_argument("--output", default="", help="Optional JSON artifact path.")
    args = parser.parse_args()

    if args.repeat <= 0:
        raise SystemExit("--repeat must be >= 1.")

    try:
        profiles = _normalize_profiles(args.profiles)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    phase_plan = _phase_commands(profiles)
    profile_tag = _profile_tag(profiles)
    output_path = (
        args.output
        or f".artifacts/quality/fault-campaign-{profile_tag}-repeat{args.repeat}.json"
    )

    results: list[dict[str, object]] = []
    failed = False
    for cycle in range(1, args.repeat + 1):
        for phase_index, (name, command) in enumerate(phase_plan, start=1):
            result = _run_phase(name, command)
            result["cycle"] = cycle
            result["cycle_phase_index"] = phase_index
            results.append(result)
            print(
                f"[fault-campaign] cycle {cycle}/{args.repeat} {name}: "
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
    accepted = cycles_completed == args.repeat and all(int(row.get("exit_code", 1)) == 0 for row in results)

    summary = {
        "profiles": profiles,
        "profile_tag": profile_tag,
        "repeat": args.repeat,
        "cycles_completed": cycles_completed,
        "phase_count": len(results),
        "passed_count": sum(1 for row in results if row.get("status") == "passed"),
        "failed_count": sum(1 for row in results if row.get("status") != "passed"),
        "accepted": accepted,
        "expected_phase_count": phase_count_per_cycle,
        "cycle_phase_counts": {str(cycle): count for cycle, count in sorted(cycle_phase_counts.items())},
        "results": results,
        "generated_at": time.time(),
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if bool(summary["accepted"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
