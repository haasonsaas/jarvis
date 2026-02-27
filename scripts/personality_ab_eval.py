#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_prompts(path: str) -> list[dict[str, str]]:
    payload = _load_json(path)
    rows = payload.get("prompts", []) if isinstance(payload, dict) else []
    prompts: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        prompt_id = str(row.get("id", "")).strip()
        context = str(row.get("context", "task")).strip().lower() or "task"
        risk = str(row.get("risk", "low")).strip().lower() or "low"
        prompt = str(row.get("prompt", "")).strip()
        if not prompt_id or not prompt:
            continue
        prompts.append({"id": prompt_id, "context": context, "risk": risk, "prompt": prompt})
    return prompts


def _load_responses(path: str) -> dict[str, str]:
    payload = _load_json(path)
    if isinstance(payload, dict) and "responses" in payload and isinstance(payload["responses"], list):
        rows = payload["responses"]
        out: dict[str, str] = {}
        for row in rows:
            if isinstance(row, dict):
                key = str(row.get("id", "")).strip()
                text = str(row.get("text", "")).strip()
                if key and text:
                    out[key] = text
        return out
    if isinstance(payload, dict):
        out: dict[str, str] = {}
        for key, value in payload.items():
            text = str(value).strip()
            if str(key).strip() and text:
                out[str(key).strip()] = text
        return out
    return {}


def _fallback_response(*, label: str, prompt: str, context: str, risk: str) -> str:
    base = {
        "task": "Understood. I will execute the plan and report concise progress.",
        "safety": "I can proceed with safeguards and clear policy checks.",
        "social": "Happy to help. I am here and ready.",
    }.get(context, "Understood.")
    if "jarvis" in label.lower():
        base = f"{base} On it."
    if risk == "high":
        base = f"{base} Please confirm before execution."
    return f"{base} Request: {prompt}"


def _word_count(text: str) -> int:
    return len(re.findall(r"[a-z0-9']+", text.lower()))


def _evaluate_variant(
    *,
    label: str,
    prompts: list[dict[str, str]],
    responses: dict[str, str],
) -> dict[str, Any]:
    context_limits = {"task": 40, "safety": 65, "social": 55}
    confirm_tokens = {"confirm", "approval", "approve"}

    rows: list[dict[str, Any]] = []
    too_verbose = 0
    friction = 0
    high_risk_total = 0
    high_risk_confirmed = 0
    total_words = 0

    for item in prompts:
        prompt_id = item["id"]
        context = item["context"]
        risk = item["risk"]
        prompt = item["prompt"]
        response = responses.get(prompt_id) or _fallback_response(
            label=label,
            prompt=prompt,
            context=context,
            risk=risk,
        )
        words = _word_count(response)
        total_words += words
        lower = response.lower()
        has_confirm = any(token in lower for token in confirm_tokens)

        limit = context_limits.get(context, 45)
        verbose = words > limit
        if verbose:
            too_verbose += 1
        if risk == "low" and has_confirm:
            friction += 1
        if risk == "high":
            high_risk_total += 1
            if has_confirm:
                high_risk_confirmed += 1

        rows.append(
            {
                "id": prompt_id,
                "context": context,
                "risk": risk,
                "words": words,
                "verbosity_limit": limit,
                "too_verbose": verbose,
                "has_confirmation_language": has_confirm,
            }
        )

    count = max(1, len(prompts))
    avg_words = total_words / count
    verbosity_rate = too_verbose / count
    friction_rate = friction / count
    confirmation_coverage = (
        (high_risk_confirmed / high_risk_total) if high_risk_total > 0 else 1.0
    )
    checks = {
        "verbosity_drift_ok": verbosity_rate <= 0.25,
        "confirmation_friction_ok": friction_rate <= 0.20,
        "high_risk_confirmation_ok": confirmation_coverage >= 0.80,
    }
    return {
        "label": label,
        "prompt_count": len(prompts),
        "avg_words": avg_words,
        "verbosity_violation_rate": verbosity_rate,
        "confirmation_friction_rate": friction_rate,
        "high_risk_confirmation_coverage": confirmation_coverage,
        "checks": checks,
        "accepted": all(bool(value) for value in checks.values()),
        "rows": rows,
    }


def _drift_summary(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    avg_a = float(a.get("avg_words", 0.0) or 0.0)
    avg_b = float(b.get("avg_words", 0.0) or 0.0)
    friction_a = float(a.get("confirmation_friction_rate", 0.0) or 0.0)
    friction_b = float(b.get("confirmation_friction_rate", 0.0) or 0.0)
    denom = max(1.0, avg_a)
    brevity_drift = (avg_b - avg_a) / denom
    friction_drift = friction_b - friction_a
    checks = {
        "brevity_drift_ok": brevity_drift <= 0.35,
        "confirmation_friction_drift_ok": friction_drift <= 0.10,
    }
    return {
        "brevity_drift_ratio": brevity_drift,
        "confirmation_friction_drift": friction_drift,
        "checks": checks,
        "accepted": all(bool(value) for value in checks.values()),
    }


def _markdown_report(summary: dict[str, Any]) -> str:
    a = summary["variant_a"]
    b = summary["variant_b"]
    drift = summary["drift"]
    lines = [
        "# Personality A/B Report",
        "",
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(summary['generated_at']))}",
        f"- Prompts: {summary['prompt_count']}",
        "",
        "## Variant A",
        f"- Label: `{a['label']}`",
        f"- Avg words: `{a['avg_words']:.2f}`",
        f"- Verbosity violation rate: `{a['verbosity_violation_rate']:.3f}`",
        f"- Confirmation friction rate: `{a['confirmation_friction_rate']:.3f}`",
        f"- High-risk confirmation coverage: `{a['high_risk_confirmation_coverage']:.3f}`",
        f"- Accepted: `{a['accepted']}`",
        "",
        "## Variant B",
        f"- Label: `{b['label']}`",
        f"- Avg words: `{b['avg_words']:.2f}`",
        f"- Verbosity violation rate: `{b['verbosity_violation_rate']:.3f}`",
        f"- Confirmation friction rate: `{b['confirmation_friction_rate']:.3f}`",
        f"- High-risk confirmation coverage: `{b['high_risk_confirmation_coverage']:.3f}`",
        f"- Accepted: `{b['accepted']}`",
        "",
        "## Drift",
        f"- Brevity drift ratio (B vs A): `{drift['brevity_drift_ratio']:.3f}`",
        f"- Confirmation friction drift (B - A): `{drift['confirmation_friction_drift']:.3f}`",
        f"- Accepted: `{drift['accepted']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate personality A/B outputs for brevity and confirmation drift.")
    parser.add_argument("--prompts", default="docs/evals/personality-ab-prompts.json")
    parser.add_argument("--responses-a", default="")
    parser.add_argument("--responses-b", default="")
    parser.add_argument("--label-a", default="composed")
    parser.add_argument("--label-b", default="jarvis")
    parser.add_argument("--output-dir", default=".artifacts/quality")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--enforce", action="store_true", help="Return non-zero when checks fail.")
    args = parser.parse_args()

    prompts = _load_prompts(args.prompts)
    responses_a = _load_responses(args.responses_a) if args.responses_a else {}
    responses_b = _load_responses(args.responses_b) if args.responses_b else {}

    variant_a = _evaluate_variant(label=args.label_a, prompts=prompts, responses=responses_a)
    variant_b = _evaluate_variant(label=args.label_b, prompts=prompts, responses=responses_b)
    drift = _drift_summary(variant_a, variant_b)

    summary = {
        "prompt_count": len(prompts),
        "variant_a": variant_a,
        "variant_b": variant_b,
        "drift": drift,
        "accepted": bool(variant_a["accepted"]) and bool(variant_b["accepted"]) and bool(drift["accepted"]),
        "generated_at": time.time(),
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "personality-ab-report.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.markdown:
        md_path = output_dir / "personality-ab-report.md"
        md_path.write_text(_markdown_report(summary), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    if args.enforce and not bool(summary["accepted"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
