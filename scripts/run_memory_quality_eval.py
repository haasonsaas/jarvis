#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional runtime dependency
    OpenAI = None  # type: ignore[assignment]


ALLOWED_ACTIONS = {"store", "skip_duplicate", "supersede", "unknown"}


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _as_text_list(value: Any) -> list[str]:
    items = _as_list(value)
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _coerce_ratio(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _tool_text(result: dict[str, Any]) -> str:
    content = result.get("content") if isinstance(result.get("content"), list) else []
    if not content:
        return ""
    row = content[0] if isinstance(content[0], dict) else {}
    return str(row.get("text", "")).strip()


def _normalize_action(value: Any) -> str:
    action = str(value or "").strip().lower()
    if action in ALLOWED_ACTIONS:
        return action
    return "unknown"


def _infer_action_from_message(text: str) -> str:
    sample = str(text or "").strip().lower()
    if "skipped as duplicate" in sample:
        return "skip_duplicate"
    if "merged into existing entry" in sample:
        return "supersede"
    if "memory stored" in sample:
        return "store"
    return "unknown"


def _contains_snippet(memory_texts: list[str], snippet: str) -> bool:
    needle = str(snippet or "").strip().lower()
    if not needle:
        return False
    return any(needle in row.lower() for row in memory_texts)


def _deterministic_mismatches(
    *,
    case: dict[str, Any],
    observed_action: str,
    final_memories: list[str],
) -> list[str]:
    mismatches: list[str] = []
    expected_actions = [_normalize_action(item) for item in _as_text_list(case.get("expected_actions"))]
    expected_actions = [item for item in expected_actions if item != "unknown"]
    if expected_actions and observed_action not in expected_actions:
        mismatches.append(
            f"observed_action not allowed (actual={observed_action!r}, expected={expected_actions!r})"
        )

    for snippet in _as_text_list(case.get("must_contain_all")):
        if not _contains_snippet(final_memories, snippet):
            mismatches.append(f"missing required memory snippet: {snippet!r}")

    must_contain_any = _as_text_list(case.get("must_contain_any"))
    if must_contain_any and not any(_contains_snippet(final_memories, snippet) for snippet in must_contain_any):
        mismatches.append("no required snippet from must_contain_any found in final memory state")

    for snippet in _as_text_list(case.get("must_not_contain")):
        if _contains_snippet(final_memories, snippet):
            mismatches.append(f"forbidden memory snippet present: {snippet!r}")

    if "max_total_memories" in case:
        try:
            max_total = int(case.get("max_total_memories"))
        except (TypeError, ValueError):
            mismatches.append("max_total_memories invalid")
        else:
            if max_total < 0:
                mismatches.append("max_total_memories invalid")
            elif len(final_memories) > max_total:
                mismatches.append(f"memory count above max ({len(final_memories)} > {max_total})")

    if "min_total_memories" in case:
        try:
            min_total = int(case.get("min_total_memories"))
        except (TypeError, ValueError):
            mismatches.append("min_total_memories invalid")
        else:
            if min_total < 0:
                mismatches.append("min_total_memories invalid")
            elif len(final_memories) < min_total:
                mismatches.append(f"memory count below min ({len(final_memories)} < {min_total})")

    return mismatches


def _normalize_judge_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    passed = bool(payload.get("passed"))
    score = _coerce_ratio(payload.get("score"), default=0.0)
    reason = str(payload.get("reason", "")).strip()
    if len(reason) > 400:
        reason = reason[:400].rstrip()
    strengths = _as_text_list(payload.get("strengths"))[:5]
    concerns = _as_text_list(payload.get("concerns"))[:5]
    return {
        "passed": passed,
        "score": score,
        "reason": reason,
        "strengths": strengths,
        "concerns": concerns,
    }


def _judge_case_with_llm(
    *,
    client: Any,
    model: str,
    case: dict[str, Any],
    observed_action: str,
    observed_message: str,
    final_memories: list[str],
) -> dict[str, Any] | None:
    if client is None:
        return None
    clean_model = str(model or "").strip()
    if not clean_model:
        return None
    system_prompt = (
        "You are scoring memory quality for a personal assistant memory mutation. "
        "Return JSON only with keys: passed (bool), score (0..1), reason (string), strengths (list), concerns (list). "
        "Reward deduplication, contradiction handling, and factual consistency. "
        "Penalize redundant memory creation, unresolved contradictions, and low-confidence unsafe rewrites."
    )
    payload = {
        "case": {
            "id": str(case.get("id", "case")),
            "objective": str(case.get("objective", "")).strip(),
            "expected_actions": _as_text_list(case.get("expected_actions")),
            "must_contain_all": _as_text_list(case.get("must_contain_all")),
            "must_contain_any": _as_text_list(case.get("must_contain_any")),
            "must_not_contain": _as_text_list(case.get("must_not_contain")),
            "max_total_memories": case.get("max_total_memories"),
            "min_total_memories": case.get("min_total_memories"),
        },
        "observed": {
            "action": observed_action,
            "message": observed_message,
            "final_memories": final_memories[:20],
        },
    }
    try:
        response = client.chat.completions.create(
            model=clean_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        )
    except Exception:
        return None
    choice = response.choices[0] if response.choices else None
    content = ""
    if choice is not None and getattr(choice, "message", None) is not None:
        content = str(getattr(choice.message, "content", "") or "")
    parsed = _extract_json_object(content)
    return _normalize_judge_payload(parsed)


def _build_config(*, project_root: Path, temp_dir: Path, openai_api_key: str):
    os.environ.setdefault("OPENAI_API_KEY", openai_api_key or "test-key-not-real")
    from jarvis.config import Config

    return Config(
        memory_path=str(temp_dir / "memory.sqlite"),
        expansion_state_path=str(temp_dir / "expansion-state.json"),
        notes_capture_dir=str(temp_dir / "notes"),
        quality_report_dir=str(temp_dir / "quality-reports"),
        release_channel_config_path=str(project_root / "config" / "release-channels.json"),
        policy_engine_path=str(project_root / "config" / "policy-engine-v1.json"),
    )


def _seed_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in _as_list(case.get("seed_memories")):
        row = _as_mapping(item)
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        rows.append(row)
    return rows


def _incoming_memory(case: dict[str, Any]) -> dict[str, Any]:
    incoming = _as_mapping(case.get("incoming_memory"))
    if incoming:
        return incoming
    return {"text": str(case.get("incoming_text", "")).strip()}


async def _execute_case(
    *,
    project_root: Path,
    case: dict[str, Any],
    openai_api_key: str,
    conflict_resolution_enabled: bool,
    conflict_model: str,
    conflict_base_url: str,
    conflict_timeout_sec: float,
    max_final_memories: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jarvis-memory-eval-") as temp_root:
        temp_dir = Path(temp_root)
        from jarvis.memory import MemoryStore
        from jarvis.tools import services

        cfg = _build_config(project_root=project_root, temp_dir=temp_dir, openai_api_key=openai_api_key)
        cfg.memory_conflict_resolution_enabled = bool(conflict_resolution_enabled)
        cfg.memory_conflict_resolution_model = str(conflict_model or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        cfg.memory_conflict_resolution_base_url = str(conflict_base_url or "").strip()
        cfg.memory_conflict_resolution_timeout_sec = max(0.5, float(conflict_timeout_sec))

        store = MemoryStore(str(temp_dir / "memory.sqlite"))
        services.bind(cfg, store)
        services.set_skill_registry(None)

        for seed in _seed_rows(case):
            seed_text = str(seed.get("text", "")).strip()
            if not seed_text:
                continue
            store.add_memory(
                seed_text,
                kind=str(seed.get("kind", "note")),
                tags=[str(tag) for tag in _as_list(seed.get("tags")) if str(tag).strip()],
                importance=_coerce_ratio(seed.get("importance"), default=0.6),
                sensitivity=_coerce_ratio(seed.get("sensitivity"), default=0.0),
                source=str(seed.get("source", "seed")),
            )

        incoming = _incoming_memory(case)
        incoming_text = str(incoming.get("text", "")).strip()
        if not incoming_text:
            return {
                "observed_action": "unknown",
                "observed_message": "incoming memory text missing",
                "final_memories": [entry.text for entry in store.recent(limit=max(1, max_final_memories))],
            }

        args = {
            "text": incoming_text,
            "kind": str(incoming.get("kind", "note")),
            "source": str(incoming.get("source", "eval_case")),
            "tags": [str(tag) for tag in _as_list(incoming.get("tags")) if str(tag).strip()],
            "importance": _coerce_ratio(incoming.get("importance"), default=0.7),
            "sensitivity": _coerce_ratio(incoming.get("sensitivity"), default=0.0),
            "inspect_candidate": True,
            "resolve_conflicts": bool(conflict_resolution_enabled),
            "conflict_resolution_model": str(incoming.get("conflict_resolution_model", conflict_model)).strip()
            or str(conflict_model).strip(),
        }
        result = await services.memory_add(args)
        observed_message = _tool_text(result)
        observed_action = _infer_action_from_message(observed_message)
        final_memories = [entry.text for entry in store.recent(limit=max(1, max_final_memories))]
        return {
            "observed_action": observed_action,
            "observed_message": observed_message,
            "final_memories": final_memories,
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
    min_avg_judge_score: float | None,
    llm_judge_mode: str,
    llm_judge_enabled: bool,
    conflict_resolution_mode: str,
    conflict_resolution_enabled: bool,
) -> dict[str, Any]:
    passed = sum(1 for row in results if bool(row.get("passed")))
    failed = len(results) - passed
    pass_rate = (passed / len(results)) if results else 0.0
    accepted = (failed == 0) if strict else (passed >= failed)

    judge_scores = [
        float(_as_mapping(row.get("llm_judge")).get("score", 0.0) or 0.0)
        for row in results
        if isinstance(row.get("llm_judge"), dict)
    ]
    avg_judge_score = (sum(judge_scores) / len(judge_scores)) if judge_scores else None

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
    if min_avg_judge_score is not None:
        if avg_judge_score is None or avg_judge_score < min_avg_judge_score:
            accepted = False
            failure_reasons.append("avg_judge_score_below_threshold")

    return {
        "dataset": str(dataset_path),
        "strict": strict,
        "thresholds": {
            "min_pass_rate": min_pass_rate,
            "max_failed": max_failed,
            "min_cases": min_cases,
            "min_avg_judge_score": min_avg_judge_score,
        },
        "execution": {
            "llm_judge_mode": llm_judge_mode,
            "llm_judge_enabled": llm_judge_enabled,
            "conflict_resolution_mode": conflict_resolution_mode,
            "conflict_resolution_enabled": conflict_resolution_enabled,
        },
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "avg_judge_score": avg_judge_score,
        "accepted": accepted,
        "failure_reasons": failure_reasons,
        "duplicate_ids": duplicate_ids,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run memory quality evaluation with optional LLM judging.")
    parser.add_argument("dataset", help="Path to memory quality dataset JSON")
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
    parser.add_argument(
        "--llm-judge",
        choices=("auto", "on", "off"),
        default="auto",
        help="Enable LLM grading for each case.",
    )
    parser.add_argument("--judge-model", default="gpt-4.1-mini")
    parser.add_argument("--judge-base-url", default="")
    parser.add_argument("--judge-timeout-sec", type=float, default=8.0)
    parser.add_argument(
        "--min-avg-judge-score",
        type=float,
        default=None,
        help="Optional minimum average LLM judge score in [0.0, 1.0].",
    )
    parser.add_argument(
        "--conflict-resolution",
        choices=("auto", "on", "off"),
        default="auto",
        help="Enable LLM conflict resolution when executing memory_add cases.",
    )
    parser.add_argument("--conflict-model", default="gpt-4.1-mini")
    parser.add_argument("--conflict-base-url", default="")
    parser.add_argument("--conflict-timeout-sec", type=float, default=5.0)
    parser.add_argument("--max-final-memories", type=int, default=20)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if args.min_pass_rate is not None and (args.min_pass_rate < 0.0 or args.min_pass_rate > 1.0):
        raise SystemExit("--min-pass-rate must be between 0.0 and 1.0.")
    if args.max_failed is not None and args.max_failed < 0:
        raise SystemExit("--max-failed must be >= 0.")
    if args.min_cases is not None and args.min_cases < 0:
        raise SystemExit("--min-cases must be >= 0.")
    if args.min_avg_judge_score is not None and (args.min_avg_judge_score < 0.0 or args.min_avg_judge_score > 1.0):
        raise SystemExit("--min-avg-judge-score must be between 0.0 and 1.0.")
    if args.judge_timeout_sec <= 0.0:
        raise SystemExit("--judge-timeout-sec must be > 0.")
    if args.conflict_timeout_sec <= 0.0:
        raise SystemExit("--conflict-timeout-sec must be > 0.")
    if args.max_final_memories < 1:
        raise SystemExit("--max-final-memories must be >= 1.")

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not isinstance(cases, list):
        raise SystemExit("Dataset format error: expected top-level object with 'cases' list.")

    case_rows = [case for case in cases if isinstance(case, dict)]
    case_ids = [str(case.get("id", "")).strip() for case in case_rows]
    id_counts: dict[str, int] = {}
    for case_id in case_ids:
        if not case_id:
            continue
        id_counts[case_id] = id_counts.get(case_id, 0) + 1
    duplicate_ids = sorted(case_id for case_id, count in id_counts.items() if count > 1)
    if not args.require_unique_ids:
        duplicate_ids = []

    openai_api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
    openai_available = OpenAI is not None and bool(openai_api_key)

    llm_judge_enabled = (
        (args.llm_judge == "on" and openai_available)
        or (args.llm_judge == "auto" and openai_available)
    )
    if args.llm_judge == "on" and not llm_judge_enabled:
        raise SystemExit("--llm-judge=on requires OPENAI_API_KEY and openai package.")

    conflict_resolution_enabled = (
        (args.conflict_resolution == "on" and openai_available)
        or (args.conflict_resolution == "auto" and openai_available)
    )
    if args.conflict_resolution == "on" and not conflict_resolution_enabled:
        raise SystemExit("--conflict-resolution=on requires OPENAI_API_KEY and openai package.")

    judge_client: Any | None = None
    if llm_judge_enabled:
        kwargs: dict[str, Any] = {"api_key": openai_api_key, "timeout": max(0.5, float(args.judge_timeout_sec))}
        if str(args.judge_base_url).strip():
            kwargs["base_url"] = str(args.judge_base_url).strip()
        try:
            judge_client = OpenAI(**kwargs)
        except Exception as exc:
            raise SystemExit(f"Failed to initialize LLM judge client: {exc}") from exc

    results: list[dict[str, Any]] = []
    for index, case in enumerate(case_rows):
        case_id = str(case.get("id", f"case_{index + 1}")).strip() or f"case_{index + 1}"
        started = time.monotonic()
        execution = asyncio.run(
            _execute_case(
                project_root=PROJECT_ROOT,
                case=case,
                openai_api_key=openai_api_key or "test-key-not-real",
                conflict_resolution_enabled=conflict_resolution_enabled,
                conflict_model=str(args.conflict_model).strip() or "gpt-4.1-mini",
                conflict_base_url=str(args.conflict_base_url).strip(),
                conflict_timeout_sec=float(args.conflict_timeout_sec),
                max_final_memories=max(1, int(args.max_final_memories)),
            )
        )

        observed_action = _normalize_action(execution.get("observed_action"))
        observed_message = str(execution.get("observed_message", ""))
        final_memories = [str(item) for item in _as_list(execution.get("final_memories"))]
        mismatches = _deterministic_mismatches(
            case=case,
            observed_action=observed_action,
            final_memories=final_memories,
        )

        llm_judge_result = None
        if llm_judge_enabled:
            llm_judge_result = _judge_case_with_llm(
                client=judge_client,
                model=str(args.judge_model).strip() or "gpt-4.1-mini",
                case=case,
                observed_action=observed_action,
                observed_message=observed_message,
                final_memories=final_memories,
            )
            if llm_judge_result is None:
                mismatches.append("llm_judge_missing_result")

        case_min_judge_score = case.get("min_judge_score", args.min_avg_judge_score)
        if case_min_judge_score is not None and isinstance(llm_judge_result, dict):
            threshold = _coerce_ratio(case_min_judge_score, default=-1.0)
            if threshold < 0.0:
                mismatches.append("min_judge_score invalid")
            else:
                score = _coerce_ratio(llm_judge_result.get("score"), default=0.0)
                if score < threshold:
                    mismatches.append(f"judge score below minimum ({score:.4f} < {threshold:.4f})")

        passed = not mismatches
        if isinstance(llm_judge_result, dict) and not bool(llm_judge_result.get("passed")):
            passed = False

        duration_ms = int((time.monotonic() - started) * 1000.0)
        results.append(
            {
                "id": case_id,
                "passed": passed,
                "observed_action": observed_action,
                "observed_message": observed_message,
                "deterministic_mismatches": mismatches,
                "llm_judge": llm_judge_result,
                "final_memories": final_memories,
                "duration_ms": duration_ms,
            }
        )

    summary = _evaluate_results(
        dataset_path=dataset_path,
        results=results,
        strict=bool(args.strict),
        min_pass_rate=args.min_pass_rate,
        max_failed=args.max_failed,
        min_cases=args.min_cases,
        duplicate_ids=duplicate_ids,
        min_avg_judge_score=args.min_avg_judge_score,
        llm_judge_mode=str(args.llm_judge),
        llm_judge_enabled=llm_judge_enabled,
        conflict_resolution_mode=str(args.conflict_resolution),
        conflict_resolution_enabled=conflict_resolution_enabled,
    )

    text = json.dumps(summary, indent=2)
    print(text)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")

    return 0 if bool(summary.get("accepted")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
