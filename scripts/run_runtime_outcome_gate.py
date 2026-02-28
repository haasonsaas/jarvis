#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content") if isinstance(result.get("content"), list) else []
    if not content:
        return {}
    row = content[0] if isinstance(content[0], dict) else {}
    text = str(row.get("text", "")).strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return _as_mapping(payload)


def _build_config(*, project_root: Path, temp_dir: Path):
    os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
    from jarvis.config import Config

    return Config(
        memory_path=str(temp_dir / "memory.sqlite"),
        expansion_state_path=str(temp_dir / "expansion-state.json"),
        notes_capture_dir=str(temp_dir / "notes"),
        quality_report_dir=str(temp_dir / "quality-reports"),
        release_channel_config_path=str(project_root / "config" / "release-channels.json"),
        policy_engine_path=str(project_root / "config" / "policy-engine-v1.json"),
    )


async def _case_high_risk_routes_to_approval_queue(project_root: Path) -> dict[str, Any]:
    case_id = "runtime_high_risk_routes_to_approval_queue"
    mismatches: list[str] = []
    with tempfile.TemporaryDirectory(prefix="jarvis-runtime-gate-") as temp_root:
        temp_dir = Path(temp_root)
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = _build_config(project_root=project_root, temp_dir=temp_dir)
        cfg.identity_enforcement_enabled = True
        cfg.identity_require_approval = True
        cfg.identity_approval_code = "super-secret-code"
        store = MemoryStore(str(temp_dir / "memory.sqlite"))
        services.bind(cfg, store)
        services.set_skill_registry(None)

        queued = await services.home_orchestrator(
            {
                "action": "execute",
                "dry_run": False,
                "confirm": True,
                "actions": [{"domain": "lock", "action": "lock", "entity_id": "lock.front_door"}],
            }
        )
        queued_payload = _tool_payload(queued)
        if queued_payload.get("approval_required") is not True:
            mismatches.append("approval_required was not true for high-risk lock execution")
        if not str(queued_payload.get("approval_id", "")).startswith("approval-"):
            mismatches.append("approval_id missing or malformed")

    return {
        "id": case_id,
        "passed": not mismatches,
        "mismatches": mismatches,
    }


async def _case_step_up_scope_binding_enforced(project_root: Path) -> dict[str, Any]:
    case_id = "runtime_step_up_scope_binding_enforced"
    mismatches: list[str] = []
    with tempfile.TemporaryDirectory(prefix="jarvis-runtime-gate-") as temp_root:
        temp_dir = Path(temp_root)
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = _build_config(project_root=project_root, temp_dir=temp_dir)
        cfg.identity_enforcement_enabled = True
        cfg.identity_require_approval = True
        cfg.identity_approval_code = "super-secret-code"
        store = MemoryStore(str(temp_dir / "memory.sqlite"))
        services.bind(cfg, store)
        services.set_skill_registry(None)
        services._policy_engine["identity"]["step_up_required_domains"] = ["lock"]

        queued_a = await services.home_orchestrator(
            {
                "action": "execute",
                "dry_run": False,
                "confirm": True,
                "actions": [{"domain": "lock", "action": "lock", "entity_id": "lock.front_door"}],
            }
        )
        payload_a = _tool_payload(queued_a)
        approval_a = str(payload_a.get("approval_id", "")).strip()
        if not approval_a:
            mismatches.append("approval A was not created")
            return {"id": case_id, "passed": False, "mismatches": mismatches}
        resolved_a = await services.home_orchestrator(
            {
                "action": "approval_resolve",
                "approval_id": approval_a,
                "approved": True,
                "__operator_identity": "session-operator",
            }
        )
        resolved_a_payload = _tool_payload(resolved_a)
        ticket_a = str(resolved_a_payload.get("execution_ticket", "")).strip()
        if not ticket_a:
            mismatches.append("approval A did not produce an execution ticket")

        queued_b = await services.home_orchestrator(
            {
                "action": "execute",
                "dry_run": False,
                "confirm": True,
                "actions": [{"domain": "lock", "action": "lock", "entity_id": "lock.back_door"}],
            }
        )
        payload_b = _tool_payload(queued_b)
        approval_b = str(payload_b.get("approval_id", "")).strip()
        if not approval_b:
            mismatches.append("approval B was not created")
            return {"id": case_id, "passed": False, "mismatches": mismatches}
        resolved_b = await services.home_orchestrator(
            {
                "action": "approval_resolve",
                "approval_id": approval_b,
                "approved": True,
                "__operator_identity": "session-operator",
            }
        )
        token_b = str(_tool_payload(resolved_b).get("step_up_token", "")).strip()
        if not token_b:
            mismatches.append("approval B did not produce a step_up_token")

        denied = await services.home_orchestrator(
            {
                "action": "execute",
                "approval_id": approval_a,
                "execution_ticket": ticket_a,
                "step_up_token": token_b,
                "__operator_identity": "session-operator",
                "dry_run": False,
                "confirm": True,
            }
        )
        denied_payload = _tool_payload(denied)
        denied_text = str(denied_payload.get("message", ""))
        if not denied_text:
            content_rows = denied.get("content") if isinstance(denied.get("content"), list) else []
            denied_text = str(_as_mapping(content_rows[0]).get("text", "")) if content_rows else ""
        if "scope does not match the approved action set" not in denied_text.lower():
            mismatches.append("scope mismatch rejection was not enforced")

    return {
        "id": case_id,
        "passed": not mismatches,
        "mismatches": mismatches,
    }


async def _case_autonomy_postcondition_defers_then_recovers(project_root: Path) -> dict[str, Any]:
    case_id = "runtime_autonomy_postcondition_defers_then_recovers"
    mismatches: list[str] = []
    with tempfile.TemporaryDirectory(prefix="jarvis-runtime-gate-") as temp_root:
        temp_dir = Path(temp_root)
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = _build_config(project_root=project_root, temp_dir=temp_dir)
        store = MemoryStore(str(temp_dir / "memory.sqlite"))
        services.bind(cfg, store)
        services.set_skill_registry(None)

        now = time.time()
        scheduled = await services.planner_engine(
            {
                "action": "autonomy_schedule",
                "title": "Runtime gate postcondition case",
                "execute_at": now - 1.0,
                "requires_checkpoint": False,
                "plan_steps": ["Apply config update"],
                "step_contracts": [
                    {
                        "postcondition": {
                            "source": "runtime",
                            "path": "config_applied",
                            "equals": True,
                        }
                    }
                ],
                "max_step_retries": 1,
                "retry_backoff_sec": 0.0,
            }
        )
        scheduled_payload = _tool_payload(scheduled)
        if int(scheduled_payload.get("step_contract_count", 0) or 0) != 1:
            mismatches.append("step contract was not persisted during schedule")

        cycle_one = await services.planner_engine(
            {
                "action": "autonomy_cycle",
                "now": now,
                "runtime_state": {"config_applied": False},
            }
        )
        cycle_one_payload = _tool_payload(cycle_one)
        cycle_one_summary = _as_mapping(cycle_one_payload.get("cycle"))
        retry_scheduled_count = cycle_one_summary.get("retry_scheduled_count", -1)
        if int(retry_scheduled_count) != 0:
            mismatches.append("postcondition enqueue should not schedule retry in same cycle")
        executed_rows = (
            cycle_one_payload.get("executed")
            if isinstance(cycle_one_payload.get("executed"), list)
            else []
        )
        executed_first = _as_mapping(executed_rows[0]) if executed_rows else {}
        step_rows = (
            executed_first.get("executed_steps")
            if isinstance(executed_first.get("executed_steps"), list)
            else []
        )
        step_first = _as_mapping(step_rows[0]) if step_rows else {}
        if str(step_first.get("verification", "")).strip().lower() != "pending_postcondition":
            mismatches.append("postcondition verification did not enter pending state")

        cycle_two = await services.planner_engine(
            {
                "action": "autonomy_cycle",
                "now": now + 2.1,
                "runtime_state": {"config_applied": True},
            }
        )
        cycle_two_payload = _tool_payload(cycle_two)
        cycle_two_summary = _as_mapping(cycle_two_payload.get("cycle"))
        if int(cycle_two_summary.get("progressed_step_count", 0) or 0) < 1:
            mismatches.append("postcondition verification did not progress task on recovery")
        cycle_two_executed = (
            cycle_two_payload.get("executed")
            if isinstance(cycle_two_payload.get("executed"), list)
            else []
        )
        cycle_two_first = _as_mapping(cycle_two_executed[0]) if cycle_two_executed else {}
        if str(cycle_two_first.get("status", "")).strip().lower() != "completed":
            mismatches.append("task was not marked completed after successful postcondition verification")

    return {
        "id": case_id,
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def _evaluate_results(
    *,
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


async def _run_cases(project_root: Path) -> list[dict[str, Any]]:
    case_functions = (
        _case_high_risk_routes_to_approval_queue,
        _case_step_up_scope_binding_enforced,
        _case_autonomy_postcondition_defers_then_recovers,
    )
    rows: list[dict[str, Any]] = []
    for case_fn in case_functions:
        try:
            rows.append(await case_fn(project_root))
        except Exception as exc:  # defensive runtime gate failure capture
            rows.append(
                {
                    "id": case_fn.__name__,
                    "passed": False,
                    "mismatches": [f"runtime_exception: {exc!r}"],
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run executable runtime outcome gate checks.")
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

    if args.min_pass_rate is not None and (args.min_pass_rate < 0.0 or args.min_pass_rate > 1.0):
        raise SystemExit("--min-pass-rate must be between 0.0 and 1.0.")
    if args.max_failed is not None and args.max_failed < 0:
        raise SystemExit("--max-failed must be >= 0.")

    results = asyncio.run(_run_cases(PROJECT_ROOT))
    summary = _evaluate_results(
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
