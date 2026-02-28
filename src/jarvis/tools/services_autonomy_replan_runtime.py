"""LLM-assisted autonomy replan draft helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from agents import Agent, Runner, set_default_openai_key
from pydantic import BaseModel, Field


class ReplanDraft(BaseModel):
    plan_steps: list[str] = Field(default_factory=list)
    step_contracts: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str = ""


def _normalized_steps(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for row in value[:40]:
        text = str(row).strip()
        if not text:
            continue
        signature = text.lower()
        if signature in seen:
            continue
        seen.add(signature)
        rows.append(text)
    return rows


def _normalized_contracts(value: Any, *, step_count: int) -> list[dict[str, Any]]:
    if step_count <= 0:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value[:step_count]:
            rows.append(dict(item) if isinstance(item, dict) else {})
    while len(rows) < step_count:
        rows.append({})
    return rows[:step_count]


def fallback_replan_draft(task_row: dict[str, Any], *, reason_code: str) -> dict[str, Any]:
    existing_steps = _normalized_steps(task_row.get("plan_steps"))
    if not existing_steps:
        title = str(task_row.get("title", "Autonomy task")).strip() or "Autonomy task"
        existing_steps = [f"Review requirements for {title}", "Re-run with validated preconditions"]

    step_index = 0
    try:
        step_index = int(task_row.get("plan_step_index", 0) or 0)
    except (TypeError, ValueError):
        step_index = 0
    if step_index < 0:
        step_index = 0
    remaining = existing_steps[step_index:] if step_index < len(existing_steps) else list(existing_steps)
    if not remaining:
        remaining = list(existing_steps)

    patched: list[str] = []
    if reason_code:
        patched.append(f"Validate blocker: {reason_code}")
    patched.extend(remaining)
    patched.append("Confirm postcondition and capture evidence")
    patched = _normalized_steps(patched)

    contracts = _normalized_contracts(task_row.get("step_contracts"), step_count=len(patched))
    return {
        "plan_steps": patched,
        "step_contracts": contracts,
        "rationale": "Fallback draft generated from remaining plan steps and latest failure reason.",
        "source": "fallback",
    }


async def generate_autonomy_replan_draft(
    services_module: Any,
    *,
    task_row: dict[str, Any],
    reason_code: str,
    phase: str,
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    s = services_module
    config = getattr(s, "_config", None)
    llm_enabled = bool(getattr(config, "autonomy_llm_replan_enabled", False))
    api_key = str(getattr(config, "openai_api_key", "")).strip() if config is not None else ""
    if not llm_enabled or not api_key:
        return fallback_replan_draft(task_row, reason_code=reason_code)

    model = (
        str(getattr(config, "openai_router_model", "")).strip()
        or str(getattr(config, "openai_model", "gpt-4.1-mini")).strip()
        or "gpt-4.1-mini"
    )
    set_default_openai_key(api_key, use_for_tracing=False)

    prompt = (
        "You are an autonomy replan writer. Produce a safer replacement plan that resolves the failure.\n"
        "Rules:\n"
        "- Return 2 to 8 concise imperative steps.\n"
        "- Preserve original task intent.\n"
        "- First step should mitigate the failure reason when possible.\n"
        "- Keep contracts optional and lightweight.\n\n"
        f"Failure reason: {reason_code}\n"
        f"Failure phase: {phase}\n"
        f"Task title: {str(task_row.get('title', 'autonomy task')).strip()}\n"
        f"Current step index: {int(task_row.get('plan_step_index', 0) or 0)}\n"
        f"Existing steps: {_normalized_steps(task_row.get('plan_steps'))}\n"
        f"Runtime snapshot preview: {str(runtime_state)[:1200]}\n"
    )

    agent = Agent(
        name="AutonomyReplanWriter",
        instructions="Return only structured draft output.",
        model=model,
        output_type=ReplanDraft,
    )

    fallback = fallback_replan_draft(task_row, reason_code=reason_code)
    try:
        result = await asyncio.wait_for(Runner.run(agent, prompt, max_turns=2), timeout=6.0)
    except Exception:
        return fallback

    output = getattr(result, "final_output", None)
    if not isinstance(output, ReplanDraft):
        try:
            output = ReplanDraft.model_validate(output)
        except Exception:
            return fallback

    steps = _normalized_steps(output.plan_steps)
    if not steps:
        return fallback
    contracts = _normalized_contracts(output.step_contracts, step_count=len(steps))
    rationale = str(output.rationale or "").strip()[:400]
    return {
        "plan_steps": steps,
        "step_contracts": contracts,
        "rationale": rationale,
        "source": "llm",
        "generated_at": time.time(),
    }
